from redis import Redis
from rq import Queue
from .config import settings

redis_conn = Redis.from_url(settings.redis_url)
android_queue = Queue("android-builds", connection=redis_conn, default_timeout=settings.build_timeout_seconds)
ios_queue = Queue("ios-builds", connection=redis_conn, default_timeout=settings.build_timeout_seconds)
