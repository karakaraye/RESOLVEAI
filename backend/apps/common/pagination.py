from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

class StandardPageNumberPagination(PageNumberPagination):
    """
    Pagination format matching the frontend Page<T> interface:
    {
      "items": [...],
      "total": number,
      "page": number,
      "pageSize": number
    }
    """
    page_size = 25
    page_size_query_param = "pageSize"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            "items": data,
            "total": self.page.paginator.count,
            "page": self.page.number,
            "pageSize": self.get_page_size(self.request),
        })
