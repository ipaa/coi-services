#!/usr/bin/env python
'''
@author Luke Campbell <LCampbell@ASAScience.com>
@date Tue Sep  4 10:03:46 EDT 2012
@file ion/services/dm/distribution/pubsub_management_service.py
@brief Publication / Subscription Management Service Implementation
'''

from interface.services.dm.ipubsub_management_service import BasePubsubManagementService
from interface.objects import StreamDefinition, Stream, Subscription, Topic
from pyon.util.arg_check import validate_true, validate_is_instance, validate_is_not_none, validate_false, validate_equal
from ion.services.dm.utility.granule_utils import ParameterDictionary
from pyon.core.exception import Conflict, BadRequest
from pyon.public import RT, PRED
from pyon.util.containers import create_unique_identifier
from pyon.util.log import log
from collections import deque

class PubsubManagementService(BasePubsubManagementService):

    #--------------------------------------------------------------------------------

    def create_stream_definition(self, name='', parameter_dictionary=None, stream_type='', description=''):
        parameter_dictionary = parameter_dictionary or {}
        existing = self.clients.resource_registry.find_resources(restype=RT.StreamDefinition, name=name, id_only=True)[0]
        if name and existing:
            stream_def = self.read_stream_definition(existing[0])
            if self._compare_pdicts(parameter_dictionary,stream_def.parameter_dictionary):
                return existing[0]
            raise Conflict('StreamDefinition with the specified name already exists. (%s)' % name)

        if not name: create_unique_identifier()

        stream_definition = StreamDefinition(parameter_dictionary=parameter_dictionary, stream_type=stream_type, name=name, description=description)
        stream_definition_id,_  = self.clients.resource_registry.create(stream_definition)

        return stream_definition_id
    
    def read_stream_definition(self, stream_definition_id=''):
        stream_definition = self.clients.resource_registry.read(stream_definition_id)
        validate_is_instance(stream_definition,StreamDefinition)
        return stream_definition

    def delete_stream_definition(self, stream_definition_id=''):
        self.read_stream_definition(stream_definition_id) # Ensures the object is a stream definition
        self.clients.resource_registry.delete(stream_definition_id)
        return True

    def compare_stream_definition(self, stream_definition1_id='', stream_definition2_id=''):
        def1 = self.read_stream_definition(stream_definition1_id)
        def2 = self.read_stream_definition(stream_definition2_id)
        return self._compare_pdicts(def1.parameter_dictionary, def2.parameter_dictionary)

    #--------------------------------------------------------------------------------
    
    def create_stream(self, name='', exchange_point='', topic_ids=None, credentials=None, stream_definition_id='', description=''):
        # Argument Validation
        if name and self.clients.resource_registry.find_resources(restype=RT.Stream,name=name,id_only=True)[0]:
            raise Conflict('The named stream already exists')

        topic_ids = topic_ids or []

        if not name: name = create_unique_identifier()

        validate_true(exchange_point, 'An exchange point must be specified')
        
        # Get topic names and topics
        topic_names = []
        associated_topics = []
        for topic_id in topic_ids:
            topic = self.read_topic(topic_id)
            if topic.exchange_point == exchange_point:
                topic_names.append(self._sanitize(topic.name))
                associated_topics.append(topic_id)
            else:
                log.warning('Attempted to attach stream %s to topic %s with different exchange points', name, topic.name)

        stream = Stream(name=name, description=description)
        routing_key = '.'.join([self._sanitize(name)] + topic_names + ['stream'])
        if len(routing_key) > 255:
            raise BadRequest('There are too many topics for this.')

        stream.stream_route.exchange_point = exchange_point
        stream.stream_route.routing_key = routing_key
        #@todo: validate credentials
        stream.stream_route.credentials = credentials

        stream_id, rev = self.clients.resource_registry.create(stream)

        if stream_definition_id: #@Todo: what if the stream has no definition?!
            self._associate_stream_with_definition(stream_id, stream_definition_id)

        for topic_id in associated_topics:
            self._associate_topic_with_stream(topic_id, stream_id)

        log.info('Stream %s: %s', name, routing_key)

        return stream_id, stream.stream_route


    def read_stream(self, stream_id=''):
        stream = self.clients.resource_registry.read(stream_id)
        validate_is_instance(stream,Stream,'The specified identifier does not correspond to a Stream resource')
        return stream

    def delete_stream(self, stream_id=''):
        self.read_stream(stream_id)

        if self._has_subscription(stream_id):
            raise BadRequest('Can not delete the stream while there are remaining subscriptions')

        self.clients.resource_registry.delete(stream_id)

        self._deassociate_stream(stream_id)

        return True

    def persist_stream(self, stream_id=''):
        stream = self.read_stream(stream_id)
        if stream.persisted:
            raise BadRequest('Stream is already persisted.')
        stream.persisted = True
        self.clients.resource_registry.update(stream)
        log.info('Stream %s marked as persisted.', stream_id)
        return True

    def unpersist_stream(self, stream_id=''):
        stream = self.read_stream(stream_id)
        if not stream.persisted:
            raise BadRequest('Stream is not persisted.')
        stream.persisted = False
        self.clients.resource_registry.update(stream)
        return True

    def is_persisted(self, stream_id=''):
        stream = self.read_stream(stream_id)
        return stream.persisted

    #--------------------------------------------------------------------------------
    
    def create_subscription(self, name='', stream_ids=None, exchange_points=None, topic_ids=None, exchange_name='', credentials=None, description=''):
        if self.clients.resource_registry.find_resources(restype=RT.Stream,name=name, id_only=True)[0]:
            raise Conflict('The named subscription already exists.')


        stream_ids      = stream_ids or []
        exchange_points = exchange_points or []
        topic_ids       = topic_ids or []

        exchange_name = exchange_name or name
        validate_true(exchange_name, 'Clients must provide an exchange name')
        log.info('Creating Subscription %s for %s <- %s', name, exchange_name, stream_ids or exchange_points or topic_ids)

        if not name: name = create_unique_identifier()

        if stream_ids:
            validate_is_instance(stream_ids, list, 'stream ids must be in list format')

        if exchange_points:
            validate_is_instance(exchange_points, list, 'exchange points must be in list format')

        if topic_ids:
            validate_is_instance(topic_ids, list, 'topic ids must be in list format')


        subscription = Subscription(name=name, description=description)
        subscription.exchange_points = exchange_points
        subscription.exchange_name   = exchange_name

        subscription_id, rev = self.clients.resource_registry.create(subscription)

        #---------------------------------
        # Associations
        #---------------------------------
        
        for stream_id in stream_ids:
            self._associate_stream_with_subscription(stream_id, subscription_id)
        
        for topic_id in topic_ids:
            self._associate_topic_with_subscription(topic_id, subscription_id)
        
        return subscription_id

    def read_subscription(self, subscription_id=''):
        subscription = self.clients.resource_registry.read(subscription_id)
        validate_is_instance(subscription,Subscription, 'The object is not of type Subscription.')
        return subscription

    def activate_subscription(self, subscription_id=''):

        validate_false(self.subscription_is_active(subscription_id), 'Subscription is already active.')

        subscription = self.read_subscription(subscription_id)

        streams, assocs = self.clients.resource_registry.find_objects(subject=subscription_id, object_type=RT.Stream, predicate=PRED.hasStream,id_only=False)
        topic_ids, assocs = self.clients.resource_registry.find_objects(subject=subscription_id, predicate=PRED.hasTopic, id_only=True)

        topic_topology = set()
        topics = []

        for topic_id in topic_ids:
            topic_tree = self._child_topics(topic_id)
            topic_topology = topic_topology.union(topic_tree)

        if topic_topology:
            topics = self.clients.resource_registry.read_mult(object_ids=list(topic_topology))

        for stream in streams:
            log.info('%s -> %s', stream.name, subscription.exchange_name)
            self._bind(stream.stream_route.exchange_point, subscription.exchange_name, stream.stream_route.routing_key)

        for exchange_point in subscription.exchange_points:
            log.info('Exchange %s -> %s', exchange_point, subscription.exchange_name)
            self._bind(exchange_point, subscription.exchange_name, '*')

        for topic in topics:
            log.info('Topic %s -> %s', topic.name, subscription.exchange_name)
            self._bind(topic.exchange_point, subscription.exchange_name, '#.%s.#' % self._sanitize(topic.name))

        subscription.activated = True
        self.clients.resource_registry.update(subscription)

    def deactivate_subscription(self, subscription_id=''):
        validate_true(self.subscription_is_active(subscription_id), 'Subscription is not active.')

        subscription = self.read_subscription(subscription_id)

        streams, assocs = self.clients.resource_registry.find_subjects(object=subscription_id, subject_type=RT.Stream, predicate=PRED.hasSubscription,id_only=False)
        topic_ids, assocs = self.clients.resource_registry.find_objects(subject=subscription_id, predicate=PRED.hasTopic, id_only=True)

        topic_topology = set()

        for topic_id in topic_ids:
            topic_tree = self._child_topics(topic_id)
            topic_topology = topic_topology.union(topic_tree)
        
        if topic_topology:
            topics = self.clients.resource_registry.read_mult(object_ids=list(topic_topology))
            for topic in topics:
                log.info('Topic %s -X-> %s', topic.name, subscription.exchange_name)
                self._unbind(topic.exchange_point, subscription.exchange_name, '#.%s.#' % self._sanitize(topic.name))

        for stream in streams:
            log.info('%s -X-> %s', stream.name, subscription.exchange_name)
            self._unbind(stream.stream_route.exchange_point, subscription.exchange_name, stream.stream_route.routing_key)

        for exchange_point in subscription.exchange_points:
            log.info('Exchange %s -X-> %s', exchange_point, subscription.exchange_name)
            self._unbind(exchange_point, subscription.exchange_name, '*')


        subscription.activated = False
        self.clients.resource_registry.update(subscription)



    def delete_subscription(self, subscription_id=''):
        if self.subscription_is_active(subscription_id):
            raise BadRequest('Clients can not delete an active subscription.')

        self._deassociate_subscription(subscription_id)

        self.clients.resource_registry.delete(subscription_id)
        return True

    #--------------------------------------------------------------------------------

    def create_topic(self, name='', exchange_point='', parent_topic_id='', description=''):
        validate_true(exchange_point, 'An exchange point must be provided for the topic')
        name = name or create_unique_identifier()
        topic = Topic(name=name, description=description, exchange_point=exchange_point)
        if parent_topic_id:
            parent_topic = self.read_topic(parent_topic_id)
            validate_equal(exchange_point, parent_topic.exchange_point, 'Can not make a sub-topic with a different exchange point')
        topic_id, rev = self.clients.resource_registry.create(topic)

        if parent_topic_id:
            self._associate_topic_with_topic(parent_topic_id, topic_id)

        return topic_id

    def read_topic(self, topic_id=''):
        topic = self.clients.resource_registry.read(topic_id)
        validate_is_instance(topic, Topic,'The specified resource is not of type Topic')
        return topic

    def delete_topic(self, topic_id=''):
        if self._has_child_topics(topic_id):
            raise BadRequest('Can not remove a parent topic, delete the children topics first')
        self.read_topic(topic_id)

        self._deassociate_topic(topic_id)
        self.clients.resource_registry.delete(topic_id)
        return True

    #--------------------------------------------------------------------------------

    def read_stream_route(self, stream_id=''):
        stream = self.read_stream(stream_id)
        return stream.stream_route

    def subscription_is_active(self, subscription_id=''):
        subscription = self.read_subscription(subscription_id)
        return subscription.activated

    #--------------------------------------------------------------------------------

    def find_streams_by_topic(self, topic_id='', id_only=False):
        pass

    def find_topics_by_name(self, topic_name='', id_only=False):
        pass

    def find_streams_by_definition(self, stream_definition_id='', id_only=False):
        subjects, assocs =self.clients.resource_registry.find_subjects(object=stream_definition_id, predicate=PRED.hasStreamDefinition, id_only=id_only)
        return subjects

    def find_topics_by_topic(self, topic_id='', id_only=False):
        topics, assocs = self.clients.resource_registry.find_objects(subject=topic_id, predicate=PRED.hasTopic,id_only=id_only)
        return topics
    
    #--------------------------------------------------------------------------------
    
    def _bind(self, exchange_point, exchange_name, binding_key):
        xp = self.container.ex_manager.create_xp(exchange_point)
        xn = self.container.ex_manager.create_xn_queue(exchange_name)
        xn.bind(binding_key, xp)

    def _unbind(self, exchange_point, exchange_name, binding_key):
        xp = self.container.ex_manager.create_xp(exchange_point)
        xn = self.container.ex_manager.create_xn_queue(exchange_name)
        xn.unbind(binding_key, xp)
    
    #--------------------------------------------------------------------------------

    def _sanitize(self, topic_name=''):
        import re
        topic_name = topic_name.lower()
        topic_name = re.sub(r'\s', '', topic_name)
        topic_name = topic_name[:24]

        return topic_name

    def _associate_topic_with_stream(self, topic_id,stream_id):
        self.clients.resource_registry.create_association(subject=stream_id, predicate=PRED.hasTopic, object=topic_id)

    def _deassociate_stream(self,stream_id):
        objects, assocs = self.clients.resource_registry.find_objects(subject=stream_id, id_only=True)
        for assoc in assocs:
            self.clients.resource_registry.delete_association(assoc)

    def _deassociate_subscription(self, subscription_id):
        objects, assocs = self.clients.resource_registry.find_objects(subject=subscription_id, id_only=True)
        for assoc in assocs:
            self.clients.resource_registry.delete_association(assoc)

    def _associate_stream_with_definition(self, stream_id,stream_definition_id):
        self.clients.resource_registry.create_association(subject=stream_id, predicate=PRED.hasStreamDefinition, object=stream_definition_id)

    def _associate_stream_with_subscription(self, stream_id, subscription_id):
        self.clients.resource_registry.create_association(subject=subscription_id, predicate=PRED.hasStream, object=stream_id)

    def _associate_topic_with_subscription(self, topic_id, subscription_id):
        self.clients.resource_registry.create_association(subject=subscription_id, predicate=PRED.hasTopic, object=topic_id)

    def _associate_topic_with_topic(self, parent_topic_id, child_topic_id):
        self.clients.resource_registry.create_association(subject=parent_topic_id, predicate=PRED.hasTopic, object=child_topic_id)

    def _deassociate_topic(self, topic_id):
        parents, assocs = self.clients.resource_registry.find_subjects(object=topic_id, id_only=True)
        for assoc in assocs:
            self.clients.resource_registry.delete_association(assoc)

    def _has_child_topics(self, topic_id):
        objects, assocs = self.clients.resource_registry.find_objects(subject=topic_id, predicate=PRED.hasTopic, id_only=True)
        return bool(len(objects))

    def _has_subscription(self, stream_id):
        subscriptions, assocs = self.clients.resource_registry.find_subjects(object=stream_id, predicate=PRED.hasStream, subject_type=RT.Stream, id_only=True)
        return bool(len(subscriptions))

    def _parent_topics(self, topic_id):
        nodes = [topic_id]
        done=False
        while not done:
            parents, assocs = self.clients.resource_registry.find_subjects(object=topic_id, predicate=PRED.hasTopic, subject_type=RT.Topic, id_only=True)
            if not parents:
                done = True
            else:
                validate_equal(len(parents),1, 'Found a topic with more than one parent.')
                topic_id = parents[0]
                nodes.append(topic_id)
        return nodes



    def _child_topics(self, topic_id):

        def edges(topic_ids=[]):
            return self.clients.resource_registry.find_associations_mult(subjects=topic_ids, id_only=True)[0]

        visited_topics = deque([topic_id] + edges([topic_id]))
        traversal_queue = deque()
        done=False
        t = None
        while not done:
            t = traversal_queue or deque(visited_topics)
            traversal_queue = deque()
            for e in edges(t):
                if not e in visited_topics:
                    visited_topics.append(e)
                    traversal_queue.append(e)
            if not len(traversal_queue): done = True

        return list(visited_topics)

    def _compare_pdicts(self, pdict1, pdict2):
        pdict1 = ParameterDictionary.load(pdict1) or {}
        pdict2 = ParameterDictionary.load(pdict2) or {}
        return bool(pdict1 == pdict2)

