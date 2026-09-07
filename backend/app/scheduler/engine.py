import logging

logger = logging.getLogger(__name__)

_scheduler = None


def get_scheduler():
    """懒加载 APScheduler；未安装时返回 None。"""
    global _scheduler
    if _scheduler is None:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.interval import IntervalTrigger
            from app.scheduler.simulators.ac_simulator import simulate_ac
            from app.scheduler.simulators.vacuum_simulator import simulate_vacuum

            scheduler = AsyncIOScheduler()
            scheduler.add_job(simulate_vacuum, IntervalTrigger(seconds=30), id="vacuum_sim")
            scheduler.add_job(simulate_ac, IntervalTrigger(seconds=60), id="ac_sim")
            _scheduler = scheduler
        except Exception:
            logger.warning("APScheduler 不可用，设备模拟引擎未启动")
            _scheduler = None
    return _scheduler


def start_scheduler():
    scheduler = get_scheduler()
    if scheduler:
        scheduler.start()
        logger.info("设备模拟引擎已启动")


def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        _scheduler = None
