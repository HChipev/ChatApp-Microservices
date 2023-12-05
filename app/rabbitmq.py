def consume_generate_question_messages(channel, callback):
    channel.queue_declare(queue='generate_question', durable=True, exclusive=False, auto_delete=True)

    channel.basic_consume(queue='generate_question', on_message_callback=callback, auto_ack=True)

    print('Waiting for messages in queue: generate_question.')

def publish_generate_answer_messages(channel, message):
    channel.queue_declare(queue='generate_answer', durable=True, exclusive=False, auto_delete=True)

    channel.basic_publish(exchange='',
                      routing_key="generate_answer",
                      body=message.encode('utf-8'))
    
    print('Published message to queue: generate_answer.')