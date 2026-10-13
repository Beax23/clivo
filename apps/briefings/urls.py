from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.briefings.api.views import (
    BriefingTemplateViewSet,
    BriefingViewSet,
    PortalBriefingView,
    PortalBriefingAnswerView,
    PortalBriefingClarificationView,
    PortalBriefingReviewView,
)
from apps.briefings.api.views.category_views import (
    BriefingTemplateCategoryViewSet,
)
from apps.briefings.views import FluxoView


templates_router = DefaultRouter()
templates_router.register(
    r'briefing-templates',
    BriefingTemplateViewSet,
    basename='briefing-template',
)

briefings_router = DefaultRouter()
briefings_router.register(
    r'briefings',
    BriefingViewSet,
    basename='briefing',
)

categories_router = DefaultRouter()
categories_router.register(
    r'briefing-template-categories',
    BriefingTemplateCategoryViewSet,
    basename='briefing-template-category',
)


urlpatterns = [
    path('fluxo/', FluxoView.as_view(), name='fluxo-page'),

    path('api/', include(categories_router.urls)),
    path('api/', include(templates_router.urls)),
    path('api/', include(briefings_router.urls)),

    path(
        'api/portal/briefings/<uuid:briefing_id>/',
        PortalBriefingView.as_view(),
        name='portal-briefing-detail',
    ),
    path(
        'api/portal/briefings/<uuid:briefing_id>/questions/<uuid:question_id>/answer/',
        PortalBriefingAnswerView.as_view(),
        name='portal-briefing-answer',
    ),
    path(
        'api/portal/briefings/<uuid:briefing_id>/questions/<uuid:question_id>/clarification/',
        PortalBriefingClarificationView.as_view(),
        name='portal-briefing-clarification',
    ),
    path(
        'api/portal/briefings/<uuid:briefing_id>/questions/<uuid:question_id>/review-request/',
        PortalBriefingReviewView.as_view(),
        name='portal-briefing-review',
    ),
]