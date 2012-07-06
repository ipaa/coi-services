#!/usr/bin/env python

'''
@package ion.processes.data.presentation
@file ion/processes/data/transforms/notification_worker.py
@author Swarbhanu Chatterjee
@brief NotificationWorker Class. An instance of this class acts as an notification worker.
'''

from pyon.public import log
from pyon.ion.transform import TransformDataProcess
from pyon.util.async import spawn
from pyon.core.exception import BadRequest
from pyon.ion.process import SimpleProcess
from pyon.event.event import EventSubscriber, EventPublisher
from ion.services.dm.utility.uns_utility_methods import send_email, load_user_info, calculate_reverse_user_info
from ion.services.dm.utility.uns_utility_methods import setting_up_smtp_client, check_user_notification_interest

class NotificationWorker(SimpleProcess):
    """
    Instances of this class acts as a Notification Worker.
    """

    def on_init(self):
        self.event_pub = EventPublisher()

    def on_start(self):
        super(NotificationWorker,self).on_start()

        #------------------------------------------------------------------------------------
        # Start by loading the user info and reverse user info dictionaries
        #------------------------------------------------------------------------------------

        # todo fix the problem of load_user_info
#        self.user_info = load_user_info()
#        calculate_reverse_user_info(self.user_info)

        #------------------------------------------------------------------------------------
        # start the event subscriber for listening to events which get generated when
        # notifications are updated.. this is required so that the notification worker can update
        # its user_info dict that it needs for batch notifications
        #------------------------------------------------------------------------------------

        def reload_user_info(event_msg, headers):

            notification_id =  event_msg.notification_id
            log.warning("In reload_user_info: Received notification with id: %s" % notification_id)

            #------------------------------------------------------------------------------------------
            # reloads the user_info and reverse_user_info dictionaries
            #------------------------------------------------------------------------------------------

            self.user_info = load_user_info()
            if self.user_info:
                self.reverse_user_info =  calculate_reverse_user_info(self.user_info)

            log.warning("After reload: ''' user_info: %s" % self.user_info)
            log.warning("After reload: ''' reverse_user_info: %s" % self.reverse_user_info)

        self.reload_user_info_subscriber = EventSubscriber(
            event_type="ReloadUserInfoEvent",
            callback=reload_user_info
        )
        self.reload_user_info_subscriber.start()

        #------------------------------------------------------------------------------------
        # start the event subscriber for all events that are of interest for notifications
        #------------------------------------------------------------------------------------

        self.event_subscriber = EventSubscriber(
            event_type="Event",
            queue_name = 'uns_queue', # modify this to point at the right queue
            callback=self.process_event
        )
        self.event_subscriber.start()

    def process_event(self, msg, headers):
        """
        From the user_info dict find out which user has subscribed to that event.
        Send email to the user
        """

        #------------------------------------------------------------------------------------
        # From the reverse user info dict find out which users have subscribed to that event
        #------------------------------------------------------------------------------------
        users = []
        if self.reverse_user_info: #todo check why we need this protection
            users = check_user_notification_interest(event = msg, reverse_user_info = self.reverse_user_info)

        #------------------------------------------------------------------------------------
        # Send email to the users
        #------------------------------------------------------------------------------------

        #todo format the message better instead of just converting the event_msg to a string
        message = str(msg)

        for user_name in users:
            smtp_client = setting_up_smtp_client()
            msg_recipient = user_info[user_name]['user_contact'].email
            send_email(message = message, msg_recipient = msg_recipient, smtp_client = smtp_client )

    def on_stop(self):
        # close subscribers safely
        self.event_subscriber.stop()
        self.reload_user_info_subscriber.stop()

    def on_quit(self):
        # close subscribers safely
        self.event_subscriber.stop()
        self.reload_user_info_subscriber.stop()

