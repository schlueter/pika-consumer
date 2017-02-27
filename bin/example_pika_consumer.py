#!/usr/bin/env python
import os
import sys

from pika_consumer import Consumer


def consume_message(body):
    print(body, file=sys.stderr)

class ExampleConsumer(Consumer):

    def on_message(self, channel, basic_deliver, properties, body):
        consume_message(body)
        self.__acknowledge_message(basic_deliver.delivery_tag)

def main():
    amqp_url = 'amqp://guest:guest@localhost:5672/%2F'
    queue = 'example_pika_consumer_queue'
    routing_key = 'example_routing_key'
    consumer = ExampleConsumer(amqp_url, queue, routing_key)

if __name__ == '__main__':
    main(
