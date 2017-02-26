import pika


parameters = pika.URLParameters('amqp://guest:guest@localhost:5672/%2F')

connection = pika.BlockingConnection(parameters)

channel = connection.channel()

channel.basic_publish('example_exchange',
                      'example_routing_key',
                      'This is an example message',
                      pika.BasicProperties(content_type='text/plain',
                                           delivery_mode=1))

connection.close()


