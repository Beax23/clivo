from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.briefings.api.views import (
    BriefingTemplateViewSet,
    BriefingViewSet,
    PortalBriefingView,
    PortalBriefingStartView,
    PortalBriefingAnswerView,
    PortalBriefingClarificationView,
    PortalBriefingReviewView,
    PortalBriefingListView,
    PortalBriefingExportPdfView,
)
from apps.briefings.api.views.category_views import (
    BriefingTemplateCategoryViewSet,
)
from apps.briefings.views import (
    FluxoView,
    BriefingDetailView,
    BriefingRawAnswersView,
    BriefingArchitectRawView,
)


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
    # ===== PÁGINA HTML DO ARQUITETO =====
    path('fluxo/', FluxoView.as_view(), name='fluxo-page'),
    path(
        'w/<str:public_id>/briefings/<uuid:briefing_id>/',
        BriefingDetailView.as_view(),
        name='briefing-detail-page',
    ),
    path(
        'w/<str:public_id>/briefings/<uuid:briefing_id>/resumo/',
        BriefingArchitectRawView.as_view(),
        name='briefing-architect-raw',
    ),

    # ===== PÁGINA HTML DO CLIENTE =====
    path(
        'portal/briefings/<uuid:briefing_id>/respostas/',
        BriefingRawAnswersView.as_view(),
        name='portal-briefing-raw-answers',
    ),

    # ===== APIs DO ARQUITETO =====
    path('api/', include(categories_router.urls)),
    path('api/', include(templates_router.urls)),
    path('api/', include(briefings_router.urls)),

    # ===== APIs DO PORTAL DO CLIENTE =====
    path(
        'api/portal/briefings/',
        PortalBriefingListView.as_view(),
        name='portal-briefing-list',
    ),
    path(
        'api/portal/briefings/<uuid:briefing_id>/',
        PortalBriefingView.as_view(),
        name='portal-briefing-detail',
    ),
    path(
        'api/portal/briefings/<uuid:briefing_id>/start/',
        PortalBriefingStartView.as_view(),
        name='portal-briefing-start',
    ),
    path(
        'api/portal/briefings/<uuid:briefing_id>/export-pdf/',
        PortalBriefingExportPdfView.as_view(),
        name='portal-briefing-export-pdf',
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