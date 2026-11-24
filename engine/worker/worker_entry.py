from redis import Redis
from rq import Queue, Worker
from engine.api.config import settings

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run a WrapForge build worker")
    parser.add_argument("--queue", choices=["android-builds", "ios-builds"], default="android-builds")
    args = parser.parse_args()
    connection = Redis.from_url(settings.redis_url)
    worker = Worker([Queue(args.queue, connection=connection)], connection=connection)
    worker.work(with_scheduler=True)
