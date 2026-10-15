from django.urls import path
from .views import (
    ComplaintTransactionsListView,
    ComplaintTransactionLinkView,
    ComplaintTransactionSearchView,
)

app_name = "transactions"

urlpatterns = [
    path(
        "complaints/<uuid:complaint_id>/transactions",
        ComplaintTransactionsListView.as_view(),
        name="complaint-transactions-list"
    ),
    path(
        "complaints/<uuid:complaint_id>/transactions/link",
        ComplaintTransactionLinkView.as_view(),
        name="complaint-transactions-link"
    ),
    path(
        "complaints/<uuid:complaint_id>/transactions/search",
        ComplaintTransactionSearchView.as_view(),
        name="complaint-transactions-search"
    ),
]
