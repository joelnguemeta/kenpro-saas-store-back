from rest_framework.pagination import PageNumberPagination

from .responses import SuccessResponse


class CustomPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return SuccessResponse(
            data={
                "results": data,
                "pagination": {
                    "current_page": self.page.number,
                    "total_pages": self.page.paginator.num_pages,
                    "total_items": self.page.paginator.count,
                    "items_per_page": self.get_page_size(self.request),
                },
            },
        )

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean", "example": True},
                "message": {
                    "type": "string",
                    "example": "Operation completed successfully.",
                },
                "data": {
                    "type": "object",
                    "properties": {
                        "results": schema,
                        "pagination": {
                            "type": "object",
                            "properties": {
                                "current_page": {"type": "integer", "example": 1},
                                "total_pages": {"type": "integer", "example": 5},
                                "total_items": {"type": "integer", "example": 42},
                                "items_per_page": {"type": "integer", "example": 10},
                            },
                        },
                    },
                },
            },
        }
