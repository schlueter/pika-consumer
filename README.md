# pika-consumer
##### Because there isn't one distributed with pika
---
An easy to use pika consumer based on the example pika asynchronous consumer. It probably works with versions of python besides 3.6, but it hasn't been tested.

## Use

With this module installed, simply extend the *pika_consumer.Consumer* class and override its *on_message* method. The *acknowledge_message* method should be called in the overriden method:

```python
from pika_consumer import Consumer

def consume_message(body):
    # do stuff with the message body

class ExampleConsumer(Consumer):

    def on_message(self, channel, basic_deliver, properties, body):
        consume_message(body)
        self.acknowledge_message(basic_deliver.delivery_tag)
```

Then set the consumer consuming:

```python
amqp_url = 'amqp://user:name@rabbit_host:5672/%2F'
queue = 'your_queue'
routing_key = 'your_routing_key'
exchange = 'your_exchange'
consumer = ExampleConsumer(amqp_url, queue, routing_key, exchange)
consumer.consume()
```

## Example

Running `vagrant up` will create a VM running rabbitmq and python 3.6 running an example consumer which will populate a file in the repo, *example.log* upon running

```
vagrant ssh -c '/usr/local/lib/pyenv/versions/3.6.0/bin/python /vagrant/bin/example_publisher.py'
```
