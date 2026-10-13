from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response

from routes.serializers import RouteRequestSerializer, RouteResponseSerializer
from routes.services.errors import PlanningError
from routes.services.planner import plan_route


def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})


def map_preview(request):
    return render(request, "routes/map.html")


@api_view(["POST"])
def optimize(request):
    serializer = RouteRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        result = plan_route(serializer.validated_data)
    except PlanningError as exc:
        return Response({"error": {"code": exc.code, "message": exc.message}}, status=exc.status)
    return Response(RouteResponseSerializer(result).data)
