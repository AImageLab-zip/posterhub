from django.contrib import admin, messages
from django.db import transaction
from .models import (
    ResearchPoster, ActivityLog, Favorite,
    ResearchGroup, ResearchInterest, UserGroupMembership,
    PosterGroupWhyUseful, BotAccount, PendingAssignmentDismissal,
    ProceedingsSource, ProceedingsPaper,
)
from .proceedings import PARSER_GUIDE
from .tasks import sync_proceedings_task


@admin.register(ResearchPoster)
class ResearchPosterAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'title',
        'authors',
        'publication_year',
        'category',
        'validation_status',
        'created_at',
        'updated_at',
    )
    list_filter = (
        'validation_status',
        'category',
        'publication_year',
        'created_at',
        'updated_at',
    )
    search_fields = (
        'title',
        'authors',
        'summary',
        'tags',
        'subfields',
    )
    readonly_fields = (
        'created_at',
        'updated_at',
    )


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'poster',
        'created_at',
    )
    list_filter = (
        'user',
        'created_at',
    )
    search_fields = (
        'user__username',
        'poster__title',
    )
    readonly_fields = (
        'created_at',
    )


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'action',
        'poster_title',
        'timestamp',
    )
    list_filter = (
        'action',
        'timestamp',
        'user',
    )
    search_fields = (
        'poster_title',
        'details',
        'user__username',
    )
    readonly_fields = (
        'timestamp',
    )


class ResearchInterestInline(admin.TabularInline):
    model = ResearchInterest
    extra = 1
    fields = ('text',)


class UserGroupMembershipInline(admin.TabularInline):
    model = UserGroupMembership
    extra = 0
    autocomplete_fields = ('user',)
    fields = ('user', 'is_primary', 'joined_at')
    readonly_fields = ('joined_at',)


@admin.register(ResearchGroup)
class ResearchGroupAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'member_count', 'poster_count', 'created_at')
    search_fields = ('name', 'interests__text', 'members__username')
    readonly_fields = ('created_at', 'updated_at')
    inlines = (ResearchInterestInline, UserGroupMembershipInline)
    filter_horizontal = ('posters',)
    ordering = ('name',)

    def member_count(self, obj):
        return obj.memberships.count()
    member_count.short_description = 'Members'

    def poster_count(self, obj):
        return obj.posters.count()
    poster_count.short_description = 'Papers'


@admin.register(ResearchInterest)
class ResearchInterestAdmin(admin.ModelAdmin):
    list_display = ('id', 'group', 'short_text', 'created_at')
    list_filter = ('group',)
    search_fields = ('text', 'group__name')
    readonly_fields = ('created_at', 'updated_at')

    def short_text(self, obj):
        return (obj.text or '')[:80]
    short_text.short_description = 'Text'


@admin.register(UserGroupMembership)
class UserGroupMembershipAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'group', 'is_primary', 'joined_at')
    list_filter = ('is_primary', 'group')
    search_fields = ('user__username', 'user__email', 'group__name')
    autocomplete_fields = ('user', 'group')
    readonly_fields = ('joined_at',)


@admin.register(PosterGroupWhyUseful)
class PosterGroupWhyUsefulAdmin(admin.ModelAdmin):
    list_display = ('id', 'poster', 'group', 'updated_at')
    list_filter = ('group',)
    search_fields = ('poster__title', 'group__name')
    autocomplete_fields = ('poster', 'group')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(PendingAssignmentDismissal)
class PendingAssignmentDismissalAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'dismissed_by', 'dismissed_at')
    search_fields = ('user__username', 'user__email')
    autocomplete_fields = ('user', 'dismissed_by')
    readonly_fields = ('dismissed_at',)


@admin.register(BotAccount)
class BotAccountAdmin(admin.ModelAdmin):
    list_display = ('id', 'platform', 'recipient', 'user', 'created_at')
    list_filter = ('platform',)
    search_fields = ('recipient', 'user__username', 'user__email')
    autocomplete_fields = ('user',)
    readonly_fields = ('created_at',)


@admin.register(ProceedingsSource)
class ProceedingsSourceAdmin(admin.ModelAdmin):
    change_list_template = 'admin/bot_engine/proceedingssource/change_list.html'
    list_display = ('conference', 'year', 'parser', 'url', 'enabled', 'paper_count', 'last_status', 'last_synced_at')
    list_editable = ('enabled',)
    list_filter = ('enabled', 'parser', 'last_status', 'conference')
    search_fields = ('conference', 'url')
    readonly_fields = ('last_synced_at', 'last_status', 'last_message', 'paper_count')
    actions = ('sync_now',)
    SYNC_FIELDS = {'url', 'parser', 'options', 'enabled'}

    @admin.action(description='Sync selected sources now')
    def sync_now(self, request, queryset):
        ids = list(queryset.filter(enabled=True).values_list('pk', flat=True))
        if not ids:
            self.message_user(request, 'Only enabled sources are synced.', messages.WARNING)
            return
        sync_proceedings_task.delay(ids)
        self.message_user(request, f'Sync queued for {len(ids)} source(s); refresh in a few minutes.')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.enabled and (not change or self.SYNC_FIELDS & set(form.changed_data)):
            transaction.on_commit(lambda: sync_proceedings_task.delay([obj.pk]))
            self.message_user(request, f'Sync queued for {obj}.')

    def changelist_view(self, request, extra_context=None):
        extra_context = {**(extra_context or {}), 'parser_guide': PARSER_GUIDE}
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(ProceedingsPaper)
class ProceedingsPaperAdmin(admin.ModelAdmin):
    list_display = ('title', 'source', 'short_authors', 'url')
    list_filter = ('source',)
    search_fields = ('title', 'authors')
    list_select_related = ('source',)

    def short_authors(self, obj):
        return (obj.authors or '')[:80]
    short_authors.short_description = 'Authors'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
