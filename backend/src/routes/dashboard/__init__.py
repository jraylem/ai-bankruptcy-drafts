"""
Dashboard router package.

Assembles all dashboard sub-routers into a single router mounted at
/api/dashboard in main.py.

URL map (all prefixed with /api/dashboard):
  kpis.py                    GET /cases
                             GET /users
                             GET /motions
                             GET /charts/motions-daily
                             GET /charts/cases-daily
                             GET /charts/motions-by-type
                             GET /system/status
                             GET /kpis/api-calls
                             GET /activity/feed

  analytics_users.py         GET /analytics/users

  analytics_users_detail.py  GET /analytics/users/{user_id}

  analytics_cases.py         GET /analytics/cases
                             GET /analytics/cases/{id}

  analytics_motions.py       GET /analytics/motions
                             GET /analytics/motions/sessions/{session_id}

  analytics_insights.py      GET /analytics/insights

  activity_log.py            GET /activity-log             (stub — TODO)

  exports.py                 GET /export/users
                             GET /export/users/{user_id}
"""

from fastapi import APIRouter

from .kpis                    import router as kpis_router
from .analytics_users         import router as analytics_users_router
from .analytics_users_detail  import router as analytics_users_detail_router
from .analytics_cases         import router as analytics_cases_router
from .analytics_motions       import router as analytics_motions_router
from .analytics_insights      import router as analytics_insights_router
from .activity_log            import router as activity_log_router
from .exports                 import router as exports_router

router = APIRouter()

# KPI / chart / system endpoints — no extra prefix
router.include_router(kpis_router)

# Analytics sub-page endpoints — mounted under /analytics
# Note: users_detail must be registered before analytics_cases to avoid
# the /{user_id} path being shadowed by a broader pattern.
router.include_router(analytics_users_router,        prefix="/analytics")
router.include_router(analytics_users_detail_router, prefix="/analytics")
router.include_router(analytics_cases_router,        prefix="/analytics")
router.include_router(analytics_motions_router,      prefix="/analytics")
router.include_router(analytics_insights_router,     prefix="/analytics")

# Activity log sub-page — mounted directly (becomes /activity-log)
router.include_router(activity_log_router)

# Export endpoints — mounted under /export
router.include_router(exports_router, prefix="/export")
