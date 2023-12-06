def consume_generate_question_messages(channel, callback):
    channel.queue_declare(queue='GenerateQuestionQueue', durable=True, exclusive=False, auto_delete=True)

    channel.basic_consume(queue='GenerateQuestionQueue', on_message_callback=callback, auto_ack=True)

    print('Waiting for messages in queue: GenerateQuestionQueue.')

def publish_generate_answer_messages(channel, message):
    channel.queue_declare(queue='GenerateAnswerQueue', durable=True, exclusive=False, auto_delete=True)

    channel.basic_publish(exchange='',
                      routing_key="GenerateAnswerQueue",
                      body=message.encode('utf-8'))
    
    print('Published message to queue: GenerateAnswerQueue.')