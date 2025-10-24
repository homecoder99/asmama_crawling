-- ============================================================================
-- Asmama Crawler Database Schema
-- ============================================================================
-- Description: PostgreSQL schema for Oliveyoung product crawling system
-- Created: 2025-01-15
-- Database: PostgreSQL 16+
-- Encoding: UTF-8
-- Total Tables: 6 (brands, categories, crawled_products, qoo10_products, brand_mapping_logs, qoo10_metrics_daily)
-- Excluded: registered_products (유저별 엑셀), qoo10_upload_fields (코드), processing_reports (파일), logs (파일)
-- ============================================================================

-- Create database (run this separately as superuser if needed)
-- CREATE DATABASE marketfeat WITH ENCODING 'UTF8' LC_COLLATE='ko_KR.UTF-8' LC_CTYPE='ko_KR.UTF-8';

-- ============================================================================
-- 1. BRANDS TABLE (UNIFIED)
-- ============================================================================
-- Purpose: 통합 브랜드 마스터 데이터
-- Sources:
--   - brand/brand.csv (36,740 rows) - Qoo10 공식 브랜드
--   - brand_translations.csv (531 rows) - 한국어 번역 캐시
--   - ban/ban.xlsx (1,637 rows) - 금지 브랜드

CREATE TABLE brands (
    brand_no VARCHAR(20) PRIMARY KEY,

    -- 브랜드명 (다국어)
    brand_title VARCHAR(255) NOT NULL,
    korean_name VARCHAR(255),
    english_name VARCHAR(255),
    japanese_name VARCHAR(255),

    -- 상태 플래그
    is_banned BOOLEAN DEFAULT FALSE,
    is_qoo10_official BOOLEAN DEFAULT TRUE,

    -- 번역 캐시 메타데이터
    translation_source VARCHAR(20),  -- 'manual', 'ai', 'qoo10'
    translation_date DATE,

    -- 타임스탬프
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for brand matching (all name variants)
CREATE INDEX idx_brand_title_normalized ON brands(LOWER(REPLACE(brand_title, ' ', '')));
CREATE INDEX idx_korean_name_normalized ON brands(LOWER(REPLACE(korean_name, ' ', '')));
CREATE INDEX idx_english_name_normalized ON brands(LOWER(REPLACE(english_name, ' ', '')));
CREATE INDEX idx_japanese_name_normalized ON brands(LOWER(REPLACE(japanese_name, ' ', '')));

-- Indexes for filtering
CREATE INDEX idx_brands_is_banned ON brands(is_banned) WHERE is_banned = TRUE;
CREATE INDEX idx_brands_is_qoo10_official ON brands(is_qoo10_official) WHERE is_qoo10_official = TRUE;

-- Full-text search index for all name columns
CREATE INDEX idx_brands_fts ON brands
USING GIN(to_tsvector('simple',
    COALESCE(brand_title, '') || ' ' ||
    COALESCE(korean_name, '') || ' ' ||
    COALESCE(english_name, '') || ' ' ||
    COALESCE(japanese_name, '')
));

COMMENT ON TABLE brands IS '통합 브랜드 마스터 데이터 (Qoo10 공식 + 번역 캐시 + 금지 브랜드)';
COMMENT ON COLUMN brands.brand_no IS '브랜드 번호 (PK, Qoo10 공식 브랜드만 보유)';
COMMENT ON COLUMN brands.korean_name IS '한국어 브랜드명 (크롤링 원본, 번역 캐시용)';
COMMENT ON COLUMN brands.is_banned IS '금지 브랜드 여부 (ban.xlsx)';
COMMENT ON COLUMN brands.is_qoo10_official IS 'Qoo10 공식 등록 브랜드 여부';
COMMENT ON COLUMN brands.translation_source IS '번역 출처: manual(수동), ai(AI생성), qoo10(Qoo10원본)';

-- ============================================================================
-- 2. CATEGORIES TABLE
-- ============================================================================
-- Purpose: Qoo10 카테고리 계층 구조
-- Source: category/Qoo10_CategoryInfo.csv (2,915 rows, all 6 columns used)

CREATE TABLE categories (
    category_code VARCHAR(9) PRIMARY KEY,
    large_code VARCHAR(9) NOT NULL,
    large_name VARCHAR(255) NOT NULL,
    medium_code VARCHAR(9) NOT NULL,
    medium_name VARCHAR(255) NOT NULL,
    small_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_category_code_length CHECK (LENGTH(category_code) = 9)
);

-- Indexes for hierarchical search
CREATE INDEX idx_large_code ON categories(large_code);
CREATE INDEX idx_medium_code ON categories(medium_code);
CREATE INDEX idx_category_names ON categories(large_name, medium_name, small_name);

COMMENT ON TABLE categories IS 'Qoo10 카테고리 3단계 계층 구조 (대/중/소)';
COMMENT ON COLUMN categories.category_code IS '카테고리 코드 9자리 (소분류)';

-- ============================================================================
-- 3. CRAWLED_PRODUCTS TABLE
-- ============================================================================
-- Purpose: Oliveyoung에서 크롤링한 원본 상품 데이터
-- Source: data/oliveyoung_YYYYMMDD.xlsx (actual 29 columns)

CREATE TABLE crawled_products (
    id SERIAL PRIMARY KEY,

    -- Required fields (17 columns)
    price INTEGER NOT NULL CHECK (price > 0),
    goods_no VARCHAR(50) NOT NULL,
    item_name TEXT NOT NULL,
    brand_name VARCHAR(255) NOT NULL,
    origin_price INTEGER NOT NULL CHECK (origin_price > 0),
    is_discounted BOOLEAN NOT NULL DEFAULT FALSE,
    benefit_info TEXT NOT NULL,
    shipping_info TEXT NOT NULL,
    refund_info TEXT NOT NULL,
    is_soldout BOOLEAN NOT NULL DEFAULT FALSE,
    images TEXT NOT NULL,  -- Delimited by '$'
    is_option_available BOOLEAN NOT NULL DEFAULT FALSE,
    unique_item_id VARCHAR(100) NOT NULL UNIQUE,
    source VARCHAR(50) NOT NULL,  -- 'oliveyoung'
    origin_product_url TEXT NOT NULL,

    -- Optional fields (12 columns)
    discount_info TEXT,  -- Mixed delimiters: $ and ||*
    others TEXT,
    option_info TEXT,  -- Delimited by ||*
    discount_start_date VARCHAR(20),
    discount_end_date VARCHAR(20),
    manufacturer VARCHAR(255),
    origin_country VARCHAR(255),
    category_main VARCHAR(100),
    category_sub VARCHAR(100),
    category_detail VARCHAR(100),
    category_main_id VARCHAR(50),
    category_sub_id VARCHAR(50),
    category_detail_id VARCHAR(50),  -- Scientific notation 방지: VARCHAR
    category_name TEXT,

    -- Metadata
    crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT uq_source_goods_no UNIQUE (source, goods_no),
    CONSTRAINT chk_goods_no_format CHECK (goods_no ~ '^[A-Z][0-9]+$')
);

-- Indexes for common queries
CREATE INDEX idx_goods_no ON crawled_products(goods_no);
CREATE INDEX idx_brand_name ON crawled_products(brand_name);
CREATE INDEX idx_unique_item_id ON crawled_products(unique_item_id);
CREATE INDEX idx_category_main ON crawled_products(category_main);
CREATE INDEX idx_category_detail_id ON crawled_products(category_detail_id);
CREATE INDEX idx_is_soldout ON crawled_products(is_soldout) WHERE is_soldout = TRUE;
CREATE INDEX idx_is_discounted ON crawled_products(is_discounted) WHERE is_discounted = TRUE;
CREATE INDEX idx_crawled_at ON crawled_products(crawled_at DESC);
CREATE INDEX idx_source ON crawled_products(source);

-- Full-text search for item name and brand
CREATE INDEX idx_crawled_products_fts ON crawled_products
USING GIN(to_tsvector('simple', item_name || ' ' || brand_name));

COMMENT ON TABLE crawled_products IS 'Oliveyoung 크롤링 원본 상품 데이터 (29개 칼럼)';
COMMENT ON COLUMN crawled_products.goods_no IS '상품번호 (A-Z로 시작하는 숫자)';
COMMENT ON COLUMN crawled_products.images IS '이미지 URL 목록 ($ 구분자)';
COMMENT ON COLUMN crawled_products.option_info IS '옵션 정보 (||* 구분자)';
COMMENT ON COLUMN crawled_products.category_detail_id IS 'float64 scientific notation 방지용 VARCHAR';

-- ============================================================================
-- 4. UPLOAD_HISTORY TABLE
-- ============================================================================
-- Purpose: 사용자별 Qoo10 업로드 이력 추적 (중복 방지용)

CREATE TABLE upload_history (
    id SERIAL PRIMARY KEY,
    crawled_product_id INTEGER NOT NULL REFERENCES crawled_products(id),
    uploaded_by VARCHAR(100) NOT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_upload_history_product_id ON upload_history(crawled_product_id);
CREATE INDEX idx_upload_history_uploaded_by ON upload_history(uploaded_by);
CREATE INDEX idx_upload_history_user_product ON upload_history(uploaded_by, crawled_product_id);
CREATE INDEX idx_upload_history_uploaded_at ON upload_history(uploaded_at DESC);

COMMENT ON TABLE upload_history IS '사용자별 Qoo10 업로드 이력 (중복 방지)';
COMMENT ON COLUMN upload_history.uploaded_by IS '업로드 유저 식별자';
COMMENT ON COLUMN upload_history.crawled_product_id IS '크롤링 원본 데이터 참조';

-- ============================================================================
-- 5. REGISTERED_PRODUCTS TABLE (DEPRECATED - upload_history로 대체)
-- ============================================================================
-- Note: registered/registered.xlsx는 레거시로 유지

-- ============================================================================
-- 6. QOO10_PRODUCTS TABLE
-- ============================================================================
-- Purpose: Qoo10 업로드용으로 변환된 상품 데이터 (48개 칼럼)
-- Source: Transformed from crawled_products via uploader/oliveyoung_uploader.py

CREATE TABLE qoo10_products (
    id SERIAL PRIMARY KEY,

    -- Qoo10 required fields
    item_number VARCHAR(255) UNIQUE,
    seller_unique_item_id VARCHAR(255) UNIQUE NOT NULL,
    category_number VARCHAR(9) NOT NULL REFERENCES categories(category_code),
    brand_number VARCHAR(20) REFERENCES brands(brand_no),
    item_name TEXT NOT NULL,
    price_yen INTEGER NOT NULL CHECK (price_yen > 0),
    image_main_url TEXT NOT NULL,
    item_description TEXT NOT NULL,

    -- Additional Qoo10 fields (40 more columns from sample.xlsx)
    item_number VARCHAR(255),
    item_name_ja TEXT,
    item_name_en TEXT,
    item_name_zh TEXT,
    search_keywords TEXT,
    model_name VARCHAR(255),
    manufacturer VARCHAR(255),
    origin_country VARCHAR(100),
    material TEXT,
    color VARCHAR(100),
    size VARCHAR(100),
    weight VARCHAR(100),
    volume VARCHAR(100),
    age_group VARCHAR(50),
    gender VARCHAR(20),
    season VARCHAR(50),
    expiry_date VARCHAR(50),
    manufacture_date VARCHAR(50),
    certification_info TEXT,
    caution_info TEXT,
    storage_method TEXT,
    usage_method TEXT,
    ingredients TEXT,
    nutritional_info TEXT,
    warranty_info TEXT,
    as_info TEXT,
    shipping_method VARCHAR(100),
    shipping_fee INTEGER,
    return_shipping_fee INTEGER,
    exchange_info TEXT,
    refund_info TEXT,
    available_coupon BOOLEAN DEFAULT TRUE,
    available_point BOOLEAN DEFAULT TRUE,
    tax_type VARCHAR(50),
    additional_images TEXT,  -- $ delimited URLs
    detail_images TEXT,  -- $ delimited URLs
    option_type VARCHAR(50),
    option_info TEXT,
    stock_quantity INTEGER,
    min_order_quantity INTEGER DEFAULT 1,
    max_order_quantity INTEGER,

    -- Metadata
    source_crawled_product_id INTEGER REFERENCES crawled_products(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    uploaded_at TIMESTAMP,

    CONSTRAINT chk_price_yen_positive CHECK (price_yen > 0)
);

-- Indexes for qoo10_products
CREATE INDEX idx_qoo10_seller_unique_item_id ON qoo10_products(seller_unique_item_id);
CREATE INDEX idx_qoo10_category_number ON qoo10_products(category_number);
CREATE INDEX idx_qoo10_brand_number ON qoo10_products(brand_number);
CREATE INDEX idx_qoo10_source_product ON qoo10_products(source_crawled_product_id);
CREATE INDEX idx_qoo10_uploaded_at ON qoo10_products(uploaded_at) WHERE uploaded_at IS NOT NULL;

COMMENT ON TABLE qoo10_products IS 'Qoo10 업로드용 변환 상품 데이터 (48개 칼럼)';
COMMENT ON COLUMN qoo10_products.source_crawled_product_id IS '원본 크롤링 데이터 FK';

-- ============================================================================
-- 6. BRAND_MAPPING_LOGS TABLE
-- ============================================================================
-- Purpose: brands 테이블 매칭 실패 로그 및 해결 추적
-- Source: output/failed_brands_*.csv

CREATE TABLE brand_mapping_logs (
    id SERIAL PRIMARY KEY,
    product_id VARCHAR(50) NOT NULL,
    korean_brand VARCHAR(255) NOT NULL,
    english_translation VARCHAR(255),
    japanese_translation VARCHAR(255),
    failed_at TIMESTAMP NOT NULL,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_brand_no VARCHAR(20) REFERENCES brands(brand_no),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_brand_log_korean ON brand_mapping_logs(korean_brand);
CREATE INDEX idx_brand_log_resolved ON brand_mapping_logs(resolved) WHERE resolved = FALSE;
CREATE INDEX idx_brand_log_failed_at ON brand_mapping_logs(failed_at DESC);
CREATE INDEX idx_brand_log_product_id ON brand_mapping_logs(product_id);

COMMENT ON TABLE brand_mapping_logs IS '브랜드 매칭 실패 로그 (시계열 추적용)';
COMMENT ON COLUMN brand_mapping_logs.resolved IS '해결 여부 (Qoo10에 브랜드 추가 후)';

-- ============================================================================
-- 7. QOO10_METRICS_DAILY TABLE
-- ============================================================================
-- Purpose: Qoo10 상품 일별 집계 지표 (판매량, 페이지뷰, 매출)
-- Source: Qoo10 셀러센터 API/크롤링

CREATE TABLE qoo10_metrics_daily (
    id BIGSERIAL PRIMARY KEY,
    metric_date DATE NOT NULL,
    qoo10_product_id INTEGER NOT NULL REFERENCES qoo10_products(id),

    -- 판매/물류 집계
    units_ordered INTEGER NOT NULL DEFAULT 0,
    units_shipped INTEGER NOT NULL DEFAULT 0,
    units_cancelled INTEGER NOT NULL DEFAULT 0,
    units_returned INTEGER NOT NULL DEFAULT 0,

    -- 금액 집계 (라인 합)
    sales_gross NUMERIC(18,2) NOT NULL DEFAULT 0,
    discount_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    buyer_paid_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    order_total_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    cogs_total NUMERIC(18,2) NOT NULL DEFAULT 0,

    -- 페이지/리뷰 지표
    pageviews INTEGER NOT NULL DEFAULT 0,
    rating_count INTEGER NOT NULL DEFAULT 0,
    rating_avg NUMERIC(3,2),

    -- 타임스탬프
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- 제약조건
    CONSTRAINT uq_qmd_date_product UNIQUE (metric_date, qoo10_product_id),
    CONSTRAINT qmd_nonneg CHECK (
        units_ordered >= 0 AND units_shipped >= 0 AND
        units_cancelled >= 0 AND units_returned >= 0 AND
        sales_gross >= 0 AND discount_amount >= 0 AND
        buyer_paid_amount >= 0 AND order_total_amount >= 0 AND
        cogs_total >= 0 AND pageviews >= 0 AND rating_count >= 0
    )
);

-- Indexes for time-series queries
CREATE INDEX idx_qmd_date ON qoo10_metrics_daily(metric_date DESC);
CREATE INDEX idx_qmd_product ON qoo10_metrics_daily(qoo10_product_id);
CREATE INDEX idx_qmd_product_date ON qoo10_metrics_daily(qoo10_product_id, metric_date DESC);

COMMENT ON TABLE qoo10_metrics_daily IS 'Qoo10 상품 일별 집계 지표 (판매/페이지뷰/매출)';
COMMENT ON COLUMN qoo10_metrics_daily.units_ordered IS '주문 수량 (당일 집계)';
COMMENT ON COLUMN qoo10_metrics_daily.buyer_paid_amount IS '구매자 실제 결제 금액';
COMMENT ON COLUMN qoo10_metrics_daily.cogs_total IS '공급원가 합계 (Cost of Goods Sold)';

-- ============================================================================
-- 8. QOO10_UPLOAD_FIELDS TABLE (EXCLUDED - 코드/설정 파일로 관리)
-- ============================================================================
-- Note: qoo10_upload_fields는 DB 테이블로 만들지 않음
-- Reason: upload/sample.xlsx는 Qoo10 업로드용 템플릿 파일

-- ============================================================================
-- 8. PROCESSING REPORTS (EXCLUDED - 파일 시스템으로 관리)
-- ============================================================================
-- Note: output/oliveyoung_processing_report_*.txt는 DB에 저장하지 않음
-- Reason: 텍스트 리포트는 파일로 관리하는 것이 더 간단하고 유연

-- ============================================================================
-- 9. APPLICATION LOGS (EXCLUDED - 파일 시스템으로 관리)
-- ============================================================================
-- Note: logs/*.log 파일은 DB에 저장하지 않음
-- Reason: 순차적 append는 파일 I/O가 더 효율적

-- ============================================================================
-- TRIGGERS
-- ============================================================================
-- Automatically update updated_at timestamp on row updates

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to all tables with updated_at column
CREATE TRIGGER update_brands_updated_at
    BEFORE UPDATE ON brands
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_categories_updated_at
    BEFORE UPDATE ON categories
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_crawled_products_updated_at
    BEFORE UPDATE ON crawled_products
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_qoo10_products_updated_at
    BEFORE UPDATE ON qoo10_products
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_brand_mapping_logs_updated_at
    BEFORE UPDATE ON brand_mapping_logs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_qoo10_metrics_daily_updated_at
    BEFORE UPDATE ON qoo10_metrics_daily
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- PERFORMANCE STATISTICS
-- ============================================================================
-- Enable statistics collection for query optimization

COMMENT ON DATABASE marketfeat IS 'Oliveyoung product crawling and Qoo10 upload system';

-- Analyze all tables for query planner statistics
ANALYZE brands;
ANALYZE categories;
ANALYZE crawled_products;
ANALYZE qoo10_products;
ANALYZE brand_mapping_logs;
ANALYZE qoo10_metrics_daily;

-- ============================================================================
-- SEED DATA NOTES
-- ============================================================================
-- To load seed data from template files into unified brands table:
--
-- 1. Load Qoo10 official brands (36,740 rows):
--    COPY brands(brand_no, brand_title, english_name, japanese_name, is_qoo10_official)
--    FROM '/path/to/brand.csv' WITH CSV HEADER ENCODING 'UTF8';
--
-- 2. Load brand translations (531 rows) and merge with existing:
--    -- Update existing brands with korean_name
--    UPDATE brands b SET korean_name = bt.korean_brand
--    FROM brand_translations_temp bt
--    WHERE b.english_name = bt.english_brand OR b.japanese_name = bt.japanese_brand;
--
-- 3. Load banned brands (1,637 rows):
--    UPDATE brands SET is_banned = TRUE WHERE brand_title IN (SELECT brand_name FROM ban_brands_temp);
--
-- 4. Load categories (2,915 rows):
--    COPY categories(category_code, large_code, large_name, medium_code, medium_name, small_name)
--    FROM '/path/to/Qoo10_CategoryInfo.csv' WITH CSV HEADER ENCODING 'UTF8';
--
-- Note: Excel files need to be converted to CSV first using pandas
--
-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
