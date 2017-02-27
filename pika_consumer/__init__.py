import logging
import pika


LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')
LOGGER = logging.getLogger(__name__)

class Consumer(object):
    """This is an inheritable consumer that will handle unexpected interactions
    with RabbitMQ such as channel and connection closures.

    If RabbitMQ closes the connection, it will reopen it. You should
    look at the output, as there are limited reasons why the connection may
    be closed, which usually are tied to permission related issues or
    socket timeouts.

    If the channel is closed, it will indicate a problem with one of the
    commands that were issued and that should surface in the output as well.

    """

    def __init__(self, amqp_url, queue, routing_key, exchange='pika', exchange_type='topic'):
        """Create a new instance of the consumer class, passing in the AMQP
        URL used to connect to RabbitMQ.

        :param str amqp_url: The AMQP url to connect with

        """

        self.exchange = exchange
        self.exchange_type = exchange_type
        self.queue = queue
        self.routing_key = routing_key
        self._connection = None
        self._channel = None
        self._closing = False
        self._consumer_tag = None
        self._url = amqp_url

    def __connect(self):
        """This method connects to RabbitMQ, returning the connection handle.
        When the connection is established, the __on_connection_open method
        will be invoked by pika.

        :rtype: pika.SelectConnection

        """
        LOGGER.info('Connecting to %s', self._url)
        return pika.SelectConnection(pika.URLParameters(self._url),
                                     self.__on_connection_open,
                                     stop_ioloop_on_close=False)

    def __on_connection_open(self, _):
        """This method is called by pika once the connection to RabbitMQ has
        been established. It passes the handle to the connection object in
        case we need it, but in this case, we'll just mark it unused.

        :type _: pika.SelectConnection

        """
        LOGGER.info('Connection opened, adding connection close callback')
        self._connection.add_on_close_callback(self.__on_connection_closed)
        LOGGER.info('Creating a new channel')
        self._connection.channel(on_open_callback=self.__on_channel_open)

    def __on_connection_closed(self, connection, reply_code, reply_text):
        """This method is invoked by pika when the connection to RabbitMQ is
        closed unexpectedly. Since it is unexpected, we will __reconnect to
        RabbitMQ if it disconnects.

        :param pika.connection.Connection connection: The closed connection obj
        :param int reply_code: The server provided reply_code if given
        :param str reply_text: The server provided reply_text if given

        """
        self._channel = None
        if self._closing:
            self._connection.ioloop.stop()
        else:
            LOGGER.warning('Connection closed, reopening in 5 seconds: (%s) %s',
                           reply_code, reply_text)
            self._connection.add_timeout(5, self.__reconnect)

    def __reconnect(self):
        """Will be invoked by the IOLoop timer if the connection is
        closed. See the __on_connection_closed method.

        """
        # This is the old connection IOLoop instance, stop its ioloop
        self._connection.ioloop.stop()

        if not self._closing:

            # Create a new connection
            self._connection = self.__connect()

            # There is now a new connection, needs a new ioloop to run
            self._connection.ioloop.start()

    def __on_channel_open(self, channel):
        """This method is invoked by pika when the channel has been opened.
        The channel object is passed in so we can make use of it.

        Since the channel is now open, we'll declare the exchange to use.

        :param pika.channel.Channel channel: The channel object

        """
        LOGGER.info('Channel opened, adding channel close callback')
        channel.add_on_close_callback(self.__on_channel_closed)
        LOGGER.info('Declaring exchange %s', self.exchange)
        channel.exchange_declare(self.__on_exchange_declareok,
                                       self.exchange,
                                       self.exchange_type)
        self._channel = channel

    def __on_channel_closed(self, channel, reply_code, reply_text):
        """Invoked by pika when RabbitMQ unexpectedly closes the channel.
        Channels are usually closed if you attempt to do something that
        violates the protocol, such as re-declare an exchange or queue with
        different parameters. In this case, we'll close the connection
        to shutdown the object.

        :param pika.channel.Channel: The closed channel
        :param int reply_code: The numeric reason the channel was closed
        :param str reply_text: The text reason the channel was closed

        """
        LOGGER.warning('Channel %i was closed: (%s) %s', channel, reply_code, reply_text)
        self._connection.close()

    def __on_exchange_declareok(self, _):
        """Invoked by pika when RabbitMQ has finished the Exchange.Declare RPC
        command.

        :param pika.Frame.Method _: Exchange.DeclareOk response frame

        """
        LOGGER.info('Exchange declared')
        LOGGER.info('Declaring queue %s', self.queue)
        self._channel.queue_declare(self.__on_queue_declareok, self.queue)

    def __on_queue_declareok(self, _):
        """Method invoked by pika when the Queue.Declare RPC call made in
        setup_queue has completed. In this method we will bind the queue
        and exchange together with the routing key by issuing the Queue.Bind
        RPC command. When this command is complete, the __on_bindok method will
        be invoked by pika.

        :param pika.frame.Method _: The Queue.DeclareOk frame

        """
        LOGGER.info('Binding %s to %s with %s',
                    self.exchange, self.queue, self.routing_key)
        self._channel.queue_bind(self.__on_bindok,
                                 self.queue,
                                 self.exchange,
                                 self.routing_key)

    def __on_bindok(self, _):
        """Invoked by pika when the Queue.Bind method has completed. At this
        point we will start consuming messages by calling start_consuming
        which will invoke the needed RPC commands to start the process.

        :param pika.frame.Method _: The Queue.BindOk response frame

        """
        LOGGER.info('Queue bound')
        LOGGER.info('Issuing consumer related RPC commands')
        LOGGER.info('Adding consumer cancellation callback')
        self._channel.add_on_cancel_callback(self.__on_consumer_cancelled)
        self._consumer_tag = self._channel.basic_consume(self.on_message,
                                                         self.queue)

    def __on_consumer_cancelled(self, method_frame):
        """Invoked by pika when RabbitMQ sends a Basic.Cancel for a consumer
        receiving messages.

        :param pika.frame.Method method_frame: The Basic.Cancel frame

        """
        LOGGER.info('Consumer was cancelled remotely, shutting down: %r',
                    method_frame)
        if self._channel:
            self._channel.close()

    def on_message(self, channel, basic_deliver, properties, body):
        """Invoked by pika when a message is delivered from RabbitMQ. The
        channel is passed for your convenience. The basic_deliver object that
        is passed in carries the exchange, routing key, delivery tag and
        a redelivered flag for the message. The properties passed in is an
        instance of BasicProperties with the message properties and the body
        is the message that was sent.

        :param pika.channel.Channel channel: The channel object
        :param pika.Spec.Basic.Deliver: basic_deliver method
        :param pika.Spec.BasicProperties: properties
        :param str|unicode body: The message body

        """
        LOGGER.info('Received message # %s from %s: %s',
                    basic_deliver.delivery_tag,
                    properties.app_id,
                    body)
        self.acknowledge_message(basic_deliver.delivery_tag)

    def acknowledge_message(self, delivery_tag):
        """Acknowledge the message delivery from RabbitMQ by sending a
        Basic.Ack RPC method for the delivery tag.

        :param int delivery_tag: The delivery tag from the Basic.Deliver frame

        """
        LOGGER.info('Acknowledging message %s', delivery_tag)
        self._channel.basic_ack(delivery_tag)

    def __on_cancelok(self, _):
        """This method is invoked by pika when RabbitMQ acknowledges the
        cancellation of a consumer. At this point we will close the channel.
        This will invoke the __on_channel_closed method once the channel has been
        closed, which will in-turn close the connection.

        :param pika.frame.Method _: The Basic.CancelOk frame

        """
        LOGGER.info('RabbitMQ acknowledged the cancellation of the consumer')
        LOGGER.info('Closing the channel')
        self._channel.close()

    def consume(self):
        """Run the example consumer by connecting to RabbitMQ and then
        starting the IOLoop to block and allow the SelectConnection to operate.

        """
        self._connection = self.__connect()
        self._connection.ioloop.start()

    def stop(self):
        """Cleanly shutdown the connection to RabbitMQ by stopping the consumer
        with RabbitMQ. When RabbitMQ confirms the cancellation, __on_cancelok
        will be invoked by pika, which will then closing the channel and
        connection. The IOLoop is started again in case this method is invoked
        in such a way which caused pika to close it prematurely. The IOLoop needs
        to be running for pika to communicate the closing requests with RabbitMQ.
        All of the commands issued prior to starting the IOLoop will be buffered
        but not processed.

        """
        LOGGER.info('Stopping')
        self._closing = True
        if self._channel:
            LOGGER.info('Sending a Basic.Cancel RPC command to RabbitMQ')
            self._channel.basic_cancel(self.__on_cancelok, self._consumer_tag)
        self._connection.ioloop.start()
        LOGGER.info('Stopped')
