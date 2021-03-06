#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Let's work with AWS SQS, here, for my Udemy course,

https://www.udemy.com/course/working-with-sqs-and-sns-aws-with-python-and-boto3-series/

Run this script as

$ for line in "$(aws-vault exec support-soak ./sqs.py)"; do echo "$line" | jq -r; done

to see the output.
"""

from typing import Any, Dict, Optional, Union, Set

import boto3
import json
import uuid

from datetime import datetime as dt


QUEUE_NAME = 'example_queue'
QUEUE_NAME_FIFO = 'example_fifo_queue.fifo'
QUEUE_NAME_DEAD = 'example_dead_queue'
QUEUE_MAIN = 'main_queue'


def sqs_client() -> Any:
    """
    Get an SQS client object.

    Returns:
        The client object we can make API calls with.
    """
    client = boto3.client('sqs')
    return client


def sqs_resource() -> Any:
    """
    Get an SQS resource object.

    Returns:
        The resource object.
    """
    resource = boto3.resource('sqs')
    return resource


def sqs_create_queue(client: Any, name: Optional[str] =None) -> Dict:
    """
    Create an SQS queue.

    Args:
        client: client object we can make API calls with.
        name: optionally set the name of the queue to something other than the default.

    Returns:
        The new SQS queue description / dict.
    """
    queue_desc = client.create_queue(
        QueueName=QUEUE_NAME if name is None else name
    )
    return queue_desc


def sqs_delete_queue(client: Any, url: Union[str, Set[str]]) -> Optional[dict]:
    """
    Delete SQS queues.

    Args:
        client: client object we can make API calls with.
        url: either a single url as a string, or a Set of unique URLs.

    Raises:
        A TypeError when url is neither a str nor a Set[str].
    """
    if isinstance(url, str):
        # Get a 'ResponseMetadata' dict back.
        return client.delete_queue(QueueUrl=url)
    elif isinstance(url, set):
        # Get a dict of URL => 'ResponseMetadata' back.
        response = dict()
        for _url in url:
            response.update({_url: client.delete_queue(QueueUrl=_url)})
        return response
    else:
        raise TypeError('Must submit either a name as a string or a set object of names.')


def sqs_create_fifo_queue(client: Any, name: Optional[str] =None) -> Dict:
    """
    Create a FIFO queue.

    Args:
        client: client object we can make API calls with.
        name: optionally set the name of the queue to something other than the default.

    Returns:
        The new FIFO SQS queue description / dict.
    """
    queue_desc = client.create_queue(
        QueueName=QUEUE_NAME_FIFO if name is None else name,
        Attributes={
            'FifoQueue': 'true'
        }
    )
    return queue_desc


def sqs_create_queue_dead_dependency(client: Any, dep_arn: str, name: Optional[str] =None) -> Dict:
    """
    Create a queue with a redrive policy pointed at another queue's ARN.

    Args:
        client: client object we can make API calls with.
        dep_arn: arn of the redrive queue.
        name: optionally set the name of the queue to something other than the default.

    Returns:
        The new dead/dep SQS queue description / dict.
    """
    policy = json.dumps({
        'deadLetterTargetArn': dep_arn,
        'maxReceiveCount': 3
    })
    sqs = client.create_queue(
        QueueName=QUEUE_MAIN if name is None else name,
        Attributes={
            'DelaySeconds': '0',
            'MaximumMessageSize': '262144',
            'VisibilityTimeout': '30',
            'MessageRetentionPeriod': '345680',
            'ReceiveMessageWaitTimeSeconds': '0',
            # Set my redrive policy.
            # https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html
            'RedrivePolicy': policy
        }
    )
    return sqs


def get_queue_arn(resource: Any, name: str) -> str:
    """
    Get a queue's ARN by name.

    Args:
        resource: resource object we can make API calls with.
        name: name of the queue.

    Returns:
        The queue's ARN.
    """
    # TODO: make this safe in the event the queue does not exist.
    arn = resource.get_queue_by_name(QueueName=name).attributes['QueueArn']
    return arn


def send_message_to_queue(client: Any, url: str, msg: dict) -> Dict:
    """
    Send a message to a queue.

    Args:
        client: client object we can make API calls with.
        url: queue to send the message to.
        msg: message to send to the queue.

    Returns:
        The response object.
    """
    response = client.send_message(
        QueueUrl=url,
        **msg
    )
    return response


def send_batch_messages(client: Any, url: str, msgs: list) -> Dict:
    """
    Send batched messages to a queue.

    Args:
        client: client object we can make API calls with.
        url: queue to send the message to.
        msgs: messages to send to the queue.

    Returns:
        The response object.
    """
    response = client.send_message_batch(
        QueueUrl=url,
        Entries=msgs
    )
    return response


def poll_queue(client: Any, url: str, max_messages: int =10) -> Dict:
    """
    Poll queue for messages. NOTE: this is not guaranteed to get me all of the messages ready to be processed on my queue.

    Args:
        client: client object we can make API calls with.
        url: queue to send the message to.

    Returns:
        The response object.
    """
    response = client.receive_message(
        QueueUrl=url,
        MaxNumberOfMessages=max_messages
    )
    return response


def process_queue(client: Any, url: str) -> None:
    """
    Process messages from a queue.

    Args:
        client: client object we can make API calls with.
        url: queue to send the message to.

    Returns:
        The response object from processing items on the SQS.
    """

    def delete_message_from_queue(receipt: str) -> Dict:
        """
        Delete a message from a queue. Only time this should be called is when we've processed it (for this script).

        Args:
            receipt: handle returned when polling messages on a queue.

        Returns:
            The response object.
        """
        nonlocal client, url
        response = client.delete_message(
            QueueUrl=url,
            ReceiptHandle=receipt
        )
        return response

    objects = poll_queue(client, url)
    if 'Messages' in objects and len(objects['Messages']) != 0:
        for message in objects['Messages']:
            print(f"Processing message: {message['MessageId']}; body: {message['Body']}")
            delete_message_from_queue(message['ReceiptHandle'])

    return None


def change_message_visibility_timeout(client: Any, url: str, receipt: str, timeout: int =5) -> Dict:
    """
    Change the visibility timeout on a queue's message.

    https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html

    Args:
        client: client object we can make API calls with.
        receipt: handle returned when polling messages on a queue.

    Returns:
        The response object.
    """
    response = client.change_message_visibility(
        QueueUrl=url,
        ReceiptHandle=receipt,
        VisibilityTimeout=timeout
    )
    return response


def purge_queue(client: Any, url: str) -> Dict:
    """
    Purge a queue of messages.

    Args:
        client: client object we can make API calls with.
        url: URL of the queue.

    Returns:
        The response object.
    """
    response = client.purge_queue(
        QueueUrl=url
    )
    return response


if __name__ == '__main__':
    client = sqs_client()
    resource = sqs_resource()
    queue_urls = set()

    ## Queue creation

    # Regular example queue (can be lossy?)
    reg_response = sqs_create_queue(client)
    QUEUE_URL_REG = reg_response['QueueUrl']
    queue_urls.add(QUEUE_URL_REG)
    print(json.dumps(reg_response))

    # FIFO queue (not lossy)
    fifo_response = sqs_create_fifo_queue(client)
    QUEUE_URL_FIFO = fifo_response['QueueUrl']
    queue_urls.add(QUEUE_URL_FIFO)
    print(json.dumps(fifo_response))

    ## Dead Letter

    # Dead letter queue
    dead_response = sqs_create_queue(client, name=QUEUE_NAME_DEAD)
    QUEUE_URL_DEAD = dead_response['QueueUrl']
    queue_urls.add(QUEUE_URL_DEAD)
    print(json.dumps(dead_response))

    # Main queue
    main_response = sqs_create_queue_dead_dependency(client, dep_arn=get_queue_arn(resource, name=QUEUE_NAME_DEAD), name=QUEUE_MAIN)
    QUEUE_URL_MAIN = main_response['QueueUrl']
    queue_urls.add(QUEUE_URL_MAIN)
    print(json.dumps(main_response))

    ## Send a Message

    # Send a single message.

    example_message = {
        'MessageAttributes': {
            'Title': {
                'DataType': 'String',
                'StringValue': 'My example message'
            },
            'Author': {
                'DataType': 'String',
                'StringValue': 'Example Author'
            },
            'Date': {
                'DataType': 'String',
                'StringValue': str(dt.now())
            }
        },
        'MessageBody': 'This is my first SQS message!!! :D :D'
    }
    send_message_response = send_message_to_queue(client, QUEUE_URL_REG, example_message)
    print(json.dumps(send_message_response))

    # Send a batch of messages.
    
    # The dict.update method here was awful. Probably some mutability issue I'm now aware of? 
    entries = [{'Id': str(uuid.uuid1()), **example_message} for _ in range(4)]
    print(json.dumps(send_batch_messages(client, QUEUE_URL_REG, entries)))

    # Poll queue
    #print(json.dumps(poll_queue(client, QUEUE_URL_REG)))

    # Process queue
    process_queue(client, QUEUE_URL_REG)

    # Purge a queue (only allowed every 60 seconds)
    #print(json.dumps(purge_queue(client, QUEUE_URL_REG)))

    ## Deletion

    # Delete all queues. Be weary of an error message like the following from a timeout.
    # botocore.errorfactory.QueueDeletedRecently: An error occurred (AWS.SimpleQueueService.QueueDeletedRecently) when calling the CreateQueue operation: You must wait 60 seconds after deleting a queue before you can create another with the same name.
    #print(json.dumps(sqs_delete_queue(client, QUEUE_URL_REG)))