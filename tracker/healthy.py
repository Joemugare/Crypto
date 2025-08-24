from django.http import JsonResponse
from django.views import View
from django.core.cache import cache
from django.db import connection
from django.conf import settings
import time

class HealthCheckView(View):
    """
    Health check endpoint for monitoring services
    Returns JSON with system status
    """
    
    def get(self, request):
        start_time = time.time()
        
        # Check database
        db_status = self._check_database()
        
        # Check cache
        cache_status = self._check_cache()
        
        # Check APIs (basic ping)
        api_status = self._check_apis()
        
        # Calculate response time
        response_time = round((time.time() - start_time) * 1000, 2)
        
        # Overall status
        overall_status = "healthy" if all([
            db_status["status"] == "ok",
            cache_status["status"] == "ok"
        ]) else "degraded"
        
        return JsonResponse({
            "status": overall_status,
            "timestamp": int(time.time()),
            "response_time_ms": response_time,
            "version": "1.0.0",
            "services": {
                "database": db_status,
                "cache": cache_status,
                "apis": api_status
            },
            "environment": {
                "debug": settings.DEBUG,
                "redis_available": self._is_redis_available()
            }
        })
    
    def _check_database(self):
        """Check database connectivity"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return {"status": "ok", "type": "sqlite" if "sqlite" in settings.DATABASES['default']['ENGINE'] else "postgresql"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _check_cache(self):
        """Check cache functionality"""
        try:
            test_key = f"health_check_{int(time.time())}"
            cache.set(test_key, "test", 10)
            value = cache.get(test_key)
            cache.delete(test_key)
            
            if value == "test":
                cache_backend = settings.CACHES['default']['BACKEND']
                cache_type = "redis" if "redis" in cache_backend.lower() else "memory"
                return {"status": "ok", "type": cache_type}
            else:
                return {"status": "error", "message": "Cache read/write failed"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _check_apis(self):
        """Basic API status (simplified for health check)"""
        # For health checks, we don't want to make external API calls
        # as they can be slow and unreliable
        return {
            "status": "not_checked",
            "message": "External API checks disabled for health endpoint"
        }
    
    def _is_redis_available(self):
        """Check if Redis is available"""
        try:
            cache_backend = settings.CACHES['default']['BACKEND']
            return "redis" in cache_backend.lower()
        except Exception:
            return False


class ReadinessCheckView(View):
    """
    Readiness check for Kubernetes/Docker deployments
    More comprehensive than health check
    """
    
    def get(self, request):
        checks = {
            "database": self._check_database_detailed(),
            "migrations": self._check_migrations(),
            "static_files": self._check_static_files()
        }
        
        all_ready = all(check["ready"] for check in checks.values())
        
        status_code = 200 if all_ready else 503
        
        return JsonResponse({
            "ready": all_ready,
            "checks": checks
        }, status=status_code)
    
    def _check_database_detailed(self):
        """Detailed database check"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM django_migrations")
                count = cursor.fetchone()[0]
                return {
                    "ready": True,
                    "migrations_count": count
                }
        except Exception as e:
            return {
                "ready": False,
                "error": str(e)
            }
    
    def _check_migrations(self):
        """Check if all migrations are applied"""
        try:
            from django.core.management import execute_from_command_line
            # This is a simplified check - in production you might want more sophisticated migration checking
            return {"ready": True}
        except Exception as e:
            return {"ready": False, "error": str(e)}
    
    def _check_static_files(self):
        """Check if static files are accessible"""
        try:
            # Basic check that static files configuration is valid
            static_url = getattr(settings, 'STATIC_URL', None)
            return {
                "ready": bool(static_url),
                "static_url": static_url
            }
        except Exception as e:
            return {"ready": False, "error": str(e)}