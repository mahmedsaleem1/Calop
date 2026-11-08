"""baseline

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-08
"""
from alembic import op
from sqlalchemy.dialects import postgresql
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table('events',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('actor_type', sa.String(), nullable=False),
    sa.Column('actor_id', sa.Uuid(), nullable=True),
    sa.Column('action', sa.Text(), nullable=False),
    sa.Column('entity_type', sa.Text(), nullable=False),
    sa.Column('entity_id', sa.Text(), nullable=False),
    sa.Column('request_id', sa.Uuid(), nullable=True),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.CheckConstraint("actor_type IN ('user', 'device', 'system', 'ai')", name='ck_events_actor_type'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_events_actor_occurred', 'events', ['actor_id', 'occurred_at'], unique=False)
    op.create_index('ix_events_entity', 'events', ['entity_type', 'entity_id'], unique=False)
    op.create_table('food_groups',
    sa.Column('id', sa.SmallInteger(), autoincrement=True, nullable=False),
    sa.Column('code', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('sort_order', sa.SmallInteger(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_table('food_sources',
    sa.Column('id', sa.SmallInteger(), autoincrement=True, nullable=False),
    sa.Column('code', sa.Text(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('publisher', sa.Text(), nullable=False),
    sa.Column('year', sa.SmallInteger(), nullable=False),
    sa.Column('url', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_table('nutrients',
    sa.Column('id', sa.SmallInteger(), autoincrement=True, nullable=False),
    sa.Column('code', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('unit', sa.Text(), nullable=False),
    sa.Column('sort_order', sa.SmallInteger(), nullable=False),
    sa.Column('is_reported', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.Text(), nullable=True),
    sa.Column('onboarding_completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('devices',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('firmware_version', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('active', 'revoked')", name='ck_devices_status'),
    sa.CheckConstraint('char_length(name) BETWEEN 1 AND 100', name='ck_devices_name_length'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('uq_devices_one_active_per_owner', 'devices', ['owner_id'], unique=True, postgresql_where=sa.text("status = 'active'"))
    op.create_table('food_search_misses',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=True),
    sa.Column('query', sa.Text(), nullable=False),
    sa.Column('normalized_query', sa.Text(), nullable=False),
    sa.Column('context', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("context IN ('app_search')", name='ck_food_search_misses_context'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('foods',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('code', sa.Text(), nullable=False),
    sa.Column('source_id', sa.SmallInteger(), nullable=False),
    sa.Column('source_ref', sa.Text(), nullable=False),
    sa.Column('group_id', sa.SmallInteger(), nullable=False),
    sa.Column('source_name', sa.Text(), nullable=False),
    sa.Column('source_local_name', sa.Text(), nullable=True),
    sa.Column('display_name', sa.Text(), nullable=False),
    sa.Column('scientific_name', sa.Text(), nullable=True),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('preparation_state', sa.String(), nullable=False),
    sa.Column('is_matchable', sa.Boolean(), nullable=False),
    sa.Column('is_searchable', sa.Boolean(), nullable=False),
    sa.Column('quality_flags', sa.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('ingredients_text', sa.Text(), nullable=True),
    sa.Column('preparation_method', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('ingredient', 'dish', 'recipe')", name='ck_foods_kind'),
    sa.CheckConstraint("preparation_state IN ('raw', 'cooked', 'processed', 'unknown')", name='ck_foods_preparation_state'),
    sa.ForeignKeyConstraint(['group_id'], ['food_groups.id'], ),
    sa.ForeignKeyConstraint(['source_id'], ['food_sources.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_table('goals',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('start_weight_kg', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('target_weight_kg', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('target_date', sa.Date(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('active', 'replaced', 'achieved')", name='ck_goals_status'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('uq_goals_one_active_per_user', 'goals', ['user_id'], unique=True, postgresql_where=sa.text("status = 'active'"))
    op.create_table('user_profiles',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('date_of_birth', sa.Date(), nullable=False),
    sa.Column('sex', sa.String(), nullable=False),
    sa.Column('height_cm', sa.Numeric(precision=5, scale=1), nullable=False),
    sa.Column('activity_level', sa.String(), nullable=False),
    sa.Column('diet_type', sa.String(), nullable=False),
    sa.Column('allergies', sa.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('timezone', sa.Text(), server_default='Asia/Karachi', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("activity_level IN ('sedentary', 'light', 'moderate', 'active', 'very_active')", name='ck_user_profiles_activity_level'),
    sa.CheckConstraint("diet_type IN ('none', 'vegetarian')", name='ck_user_profiles_diet_type'),
    sa.CheckConstraint("sex IN ('male', 'female')", name='ck_user_profiles_sex'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('weight_entries',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('weight_kg', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('source', sa.String(), nullable=False),
    sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("source IN ('onboarding', 'settings')", name='ck_weight_entries_source'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_weight_entries_user_recorded', 'weight_entries', ['user_id', sa.literal_column('recorded_at DESC')], unique=False)
    op.create_table('captures',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('source', sa.String(), nullable=False),
    sa.Column('device_id', sa.Uuid(), nullable=True),
    sa.Column('weight_g', sa.Numeric(precision=7, scale=1), nullable=True),
    sa.Column('weight_source', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('selected_food_id', sa.Integer(), nullable=True),
    sa.Column('not_in_catalog_label', sa.Text(), nullable=True),
    sa.Column('image_status', sa.String(), nullable=False),
    sa.Column('image_local_path', sa.Text(), nullable=True),
    sa.Column('image_url', sa.Text(), nullable=True),
    sa.Column('image_public_id', sa.Text(), nullable=True),
    sa.Column('image_bytes', sa.Integer(), nullable=False),
    sa.Column('image_sha256', sa.CHAR(length=64), nullable=False),
    sa.Column('captured_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('recognized_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('firmware_version', sa.Text(), nullable=True),
    sa.Column('app_version', sa.Text(), nullable=True),
    sa.CheckConstraint("(source = 'device' AND device_id IS NOT NULL AND weight_source = 'measured' AND weight_g IS NOT NULL) OR (source = 'phone' AND device_id IS NULL AND weight_source = 'user_estimate')", name='ck_captures_source_rules'),
    sa.CheckConstraint("image_status IN ('local', 'uploaded', 'upload_failed')", name='ck_captures_image_status'),
    sa.CheckConstraint("source IN ('device', 'phone')", name='ck_captures_source'),
    sa.CheckConstraint("status IN ('identifying', 'awaiting_weight', 'needs_review', 'logged', 'discarded', 'failed')", name='ck_captures_status'),
    sa.CheckConstraint("weight_source IN ('measured', 'user_estimate')", name='ck_captures_weight_source'),
    sa.CheckConstraint('weight_g IS NULL OR weight_g > 0', name='ck_captures_weight_positive'),
    sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
    sa.ForeignKeyConstraint(['selected_food_id'], ['foods.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_captures_user_open_status', 'captures', ['user_id', 'status'], unique=False, postgresql_where=sa.text("status IN ('identifying', 'awaiting_weight', 'needs_review')"))
    op.create_index('ix_captures_user_received', 'captures', ['user_id', sa.literal_column('received_at DESC')], unique=False)
    op.create_table('device_api_keys',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('device_id', sa.Uuid(), nullable=False),
    sa.Column('key_hash', sa.CHAR(length=64), nullable=False),
    sa.Column('key_prefix', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key_hash')
    )
    op.create_index('uq_device_api_keys_one_live_per_device', 'device_api_keys', ['device_id'], unique=True, postgresql_where=sa.text('revoked_at IS NULL'))
    op.create_table('food_aliases',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('food_id', sa.Integer(), nullable=False),
    sa.Column('alias', sa.Text(), nullable=False),
    sa.Column('normalized_alias', sa.Text(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('is_preferred', sa.Boolean(), nullable=False),
    sa.CheckConstraint("kind IN ('source', 'local', 'common', 'spelling')", name='ck_food_aliases_kind'),
    sa.ForeignKeyConstraint(['food_id'], ['foods.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('food_id', 'normalized_alias', name='uq_food_aliases_food_alias')
    )
    op.create_index('ix_food_aliases_trgm', 'food_aliases', ['normalized_alias'], unique=False, postgresql_using='gin', postgresql_ops={'normalized_alias': 'gin_trgm_ops'})
    op.create_index('uq_food_aliases_preferred', 'food_aliases', ['normalized_alias'], unique=True, postgresql_where=sa.text('is_preferred'))
    op.create_table('food_nutrients',
    sa.Column('food_id', sa.Integer(), nullable=False),
    sa.Column('nutrient_id', sa.SmallInteger(), nullable=False),
    sa.Column('amount_per_100g', sa.Numeric(precision=10, scale=3), nullable=False),
    sa.ForeignKeyConstraint(['food_id'], ['foods.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['nutrient_id'], ['nutrients.id'], ),
    sa.PrimaryKeyConstraint('food_id', 'nutrient_id')
    )
    op.create_table('nutrition_targets',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('goal_id', sa.Uuid(), nullable=True),
    sa.Column('effective_from', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('maintenance_kcal', sa.Numeric(precision=7, scale=1), nullable=False),
    sa.Column('daily_adjustment_kcal', sa.Numeric(precision=7, scale=1), nullable=False),
    sa.Column('energy_kcal', sa.Numeric(precision=7, scale=1), nullable=False),
    sa.Column('protein_g', sa.Numeric(precision=6, scale=1), nullable=False),
    sa.Column('fat_g', sa.Numeric(precision=6, scale=1), nullable=False),
    sa.Column('carbohydrate_g', sa.Numeric(precision=6, scale=1), nullable=False),
    sa.Column('floor_applied', sa.Boolean(), nullable=False),
    sa.Column('method', sa.Text(), nullable=False),
    sa.Column('inputs', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.ForeignKeyConstraint(['goal_id'], ['goals.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_nutrition_targets_user_effective', 'nutrition_targets', ['user_id', sa.literal_column('effective_from DESC')], unique=False)
    op.create_table('food_log_entries',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('capture_id', sa.Uuid(), nullable=False),
    sa.Column('food_id', sa.Integer(), nullable=False),
    sa.Column('weight_g', sa.Numeric(precision=7, scale=1), nullable=False),
    sa.Column('weight_source', sa.String(), nullable=False),
    sa.Column('resolution', sa.String(), nullable=False),
    sa.Column('eaten_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('local_date', sa.Date(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("resolution IN ('auto', 'user_selected', 'user_corrected')", name='ck_food_log_entries_resolution'),
    sa.CheckConstraint("weight_source IN ('measured', 'user_estimate')", name='ck_food_log_entries_weight_source'),
    sa.ForeignKeyConstraint(['capture_id'], ['captures.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['food_id'], ['foods.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('capture_id')
    )
    op.create_index('ix_food_log_entries_user_date', 'food_log_entries', ['user_id', 'local_date'], unique=False)
    op.create_table('jobs',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('capture_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('attempts', sa.SmallInteger(), server_default='0', nullable=False),
    sa.Column('max_attempts', sa.SmallInteger(), nullable=False),
    sa.Column('run_after', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('recognize_capture', 'upload_image')", name='ck_jobs_kind'),
    sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name='ck_jobs_status'),
    sa.ForeignKeyConstraint(['capture_id'], ['captures.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_jobs_capture_id'), 'jobs', ['capture_id'], unique=False)
    op.create_index('ix_jobs_status_run_after', 'jobs', ['status', 'run_after'], unique=False)
    op.create_table('recognition_runs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('capture_id', sa.Uuid(), nullable=False),
    sa.Column('attempt', sa.SmallInteger(), nullable=False),
    sa.Column('provider', sa.Text(), nullable=False),
    sa.Column('model', sa.Text(), nullable=False),
    sa.Column('prompt_version', sa.Text(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('decision', sa.String(), nullable=True),
    sa.Column('top_confidence', sa.Numeric(precision=4, scale=3), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=True),
    sa.Column('input_tokens', sa.Integer(), nullable=True),
    sa.Column('output_tokens', sa.Integer(), nullable=True),
    sa.Column('error_code', sa.Text(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('raw_response', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("decision IS NULL OR decision IN ('auto_logged', 'needs_review')", name='ck_recognition_runs_decision'),
    sa.CheckConstraint("status IN ('running', 'succeeded', 'failed', 'rate_limited')", name='ck_recognition_runs_status'),
    sa.ForeignKeyConstraint(['capture_id'], ['captures.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_recognition_runs_capture_id'), 'recognition_runs', ['capture_id'], unique=False)
    op.create_table('food_log_entry_nutrients',
    sa.Column('entry_id', sa.Uuid(), nullable=False),
    sa.Column('nutrient_id', sa.SmallInteger(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=10, scale=3), nullable=False),
    sa.ForeignKeyConstraint(['entry_id'], ['food_log_entries.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['nutrient_id'], ['nutrients.id'], ),
    sa.PrimaryKeyConstraint('entry_id', 'nutrient_id')
    )
    op.create_table('recognition_candidates',
    sa.Column('run_id', sa.Uuid(), nullable=False),
    sa.Column('rank', sa.SmallInteger(), nullable=False),
    sa.Column('returned_code', sa.Text(), nullable=False),
    sa.Column('food_id', sa.Integer(), nullable=True),
    sa.Column('confidence', sa.Numeric(precision=4, scale=3), nullable=False),
    sa.ForeignKeyConstraint(['food_id'], ['foods.id'], ),
    sa.ForeignKeyConstraint(['run_id'], ['recognition_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('run_id', 'rank')
    )


def downgrade() -> None:
    op.drop_table('recognition_candidates')
    op.drop_table('food_log_entry_nutrients')
    op.drop_table('recognition_runs')
    op.drop_table('jobs')
    op.drop_table('food_log_entries')
    op.drop_table('nutrition_targets')
    op.drop_table('food_nutrients')
    op.drop_table('food_aliases')
    op.drop_table('device_api_keys')
    op.drop_table('captures')
    op.drop_table('weight_entries')
    op.drop_table('user_profiles')
    op.drop_table('goals')
    op.drop_table('foods')
    op.drop_table('food_search_misses')
    op.drop_table('devices')
    op.drop_table('users')
    op.drop_table('nutrients')
    op.drop_table('food_sources')
    op.drop_table('food_groups')
    op.drop_table('events')
