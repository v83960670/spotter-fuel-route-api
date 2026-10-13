from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is not None:
        response.data = {
            "error": {
                "code": getattr(exc, "default_code", "invalid_request"),
                "details": response.data,
            }
        }
    return response
