"""" Example kafka_main.py - how to interact with pub_sub_module

Run a consumer: python kafka_main.py consume
Run a producer: python kafka_main.py produce

"""

import logging
import sys

from pub_sub import KafkaPublisher, KafkaSubscriber

logging.basicConfig(level=logging.INFO)

TOPIC = "demo-events"


def run_producer() -> None:
    with KafkaPublisher() as pub:
        for i in range(5):
            pub.publish(TOPIC, {"event_id": i, "message": f"hello #{i}"}, key=str(i))
            print(f"Published event {i}")

def handle_message(topic: str, value:dict) -> None:
    print(f"[{topoic}] received: {value}")



def run_consumer() -> None:
    sub = KafkaSubscriber(group_id="main-app")
    sub.subscribe([TOPIC], handler=handle_message)  # blocks until Ctrl+c


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "consume"
    run_producer() if mode == "produce" else run_consumer()