import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import NotAuthenticated, AuthenticationFailed

logger = logging.getLogger("resolveai.exceptions")

def custom_exception_handler(exc, context):
    """
    Standardize all API error responses to:
        { "message": "Clear explanation of the error." }
    This precisely matches the Next.js frontend's ApiError wire format.
    Ensures unauthenticated requests return HTTP 401 with standard "Sign in to continue." copy.
    """
    response = exception_handler(exc, context)

    if response is not None:
        # Enforce HTTP 401 and standard copy for unauthenticated requests
        if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
            response.status_code = status.HTTP_401_UNAUTHORIZED
            response.data = {"message": "Sign in to continue."}
            return response

        message = "An error occurred."
        if isinstance(response.data, dict):
            if "message" in response.data:
                message = str(response.data["message"])
            elif "detail" in response.data:
                message = str(response.data["detail"])
            else:
                first_key = next(iter(response.data))
                val = response.data[first_key]
                if isinstance(val, list) and len(val) > 0:
                    message = f"{first_key}: {val[0]}"
                elif isinstance(val, dict):
                    inner_key = next(iter(val))
                    message = f"{first_key}.{inner_key}: {val[inner_key]}"
                else:
                    message = f"{first_key}: {val}"
        elif isinstance(response.data, list) and len(response.data) > 0:
            message = str(response.data[0])

        response.data = {"message": message}
        return response

    # Unhandled server exceptions (HTTP 500)
    logger.exception(f"Unhandled exception during request processing: {exc}")
    return Response(
        {"message": "An unexpected server error occurred. Please try again shortly."},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )
