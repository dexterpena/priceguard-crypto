-- Drop all tables in correct order (respecting dependencies)
DROP TABLE IF EXISTS alerts_log CASCADE;
DROP TABLE IF EXISTS watchlist CASCADE;
DROP TABLE IF EXISTS user_preferences CASCADE;
DROP TABLE IF EXISTS popular_cryptos CASCADE;
DROP TABLE IF EXISTS cryptos CASCADE;
DROP TABLE IF EXISTS price_history CASCADE;

-- Drop all functions
DROP FUNCTION IF EXISTS is_popular_cryptos_cache_stale() CASCADE;
DROP FUNCTION IF EXISTS get_cached_crypto_info(INTEGER) CASCADE;
DROP FUNCTION IF EXISTS update_watchlist_cache_from_popular() CASCADE;

-- TABLE 1: popular_cryptos (Cache Table)

-- Caches top cryptocurrencies from CoinDesk API
-- Updated every 5 minutes by background job
CREATE TABLE popular_cryptos (
    api_id INTEGER PRIMARY KEY,           -- CoinDesk API ID (e.g., 1 for BTC)
    symbol VARCHAR(10) NOT NULL,          -- e.g., 'BTC'
    name VARCHAR(100) NOT NULL,           -- e.g., 'Bitcoin'
    logo_url TEXT,                        -- Logo from CoinDesk
    price NUMERIC(20,8) NOT NULL,         -- Current price in USD
    market_cap NUMERIC(20,2),             -- Market capitalization
    volume_24h NUMERIC(20,2),             -- 24h trading volume
    change_24h NUMERIC(10,4),             -- 24h percentage change
    price_updated_at TIMESTAMP NOT NULL,  -- When API last updated price
    cached_at TIMESTAMP DEFAULT NOW(),    -- When first cached
    updated_at TIMESTAMP DEFAULT NOW()    -- When last refreshed
);

-- Indexes for fast queries
CREATE INDEX idx_popular_cryptos_symbol ON popular_cryptos(symbol);
CREATE INDEX idx_popular_cryptos_updated_at ON popular_cryptos(updated_at DESC);
CREATE INDEX idx_popular_cryptos_market_cap ON popular_cryptos(market_cap DESC);

-- TABLE 2: watchlist

-- User's watched cryptocurrencies with price alerts
CREATE TABLE watchlist (
    watch_id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    api_crypto_id INTEGER NOT NULL,       -- CoinDesk API ID
    symbol VARCHAR(10),                   -- Cached from popular_cryptos
    name VARCHAR(100),                    -- Cached from popular_cryptos
    logo_url TEXT,                        -- Cached from popular_cryptos
    alert_percent NUMERIC(5,2) DEFAULT 5.0,  -- Alert threshold (e.g., ±5%)
    date_added TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, api_crypto_id)       -- User can't add same crypto twice
);

-- Indexes
CREATE INDEX idx_watchlist_user ON watchlist(user_id);
CREATE INDEX idx_watchlist_api_crypto ON watchlist(api_crypto_id);
CREATE INDEX idx_watchlist_user_crypto ON watchlist(user_id, api_crypto_id);

-- TABLE 3: alerts_log

-- History of triggered price alerts
CREATE TABLE alerts_log (
    alert_id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    api_crypto_id INTEGER NOT NULL,       -- CoinDesk API ID
    symbol VARCHAR(10),                   -- For display
    name VARCHAR(100),                    -- For display
    trigger_price NUMERIC(20,8) NOT NULL, -- Price that triggered alert
    percent_change NUMERIC(10,4) NOT NULL,-- Percentage change that triggered
    alert_type VARCHAR(10) NOT NULL CHECK (alert_type IN ('increase', 'decrease')),
    timestamp TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_alerts_log_user ON alerts_log(user_id);
CREATE INDEX idx_alerts_log_api_crypto ON alerts_log(api_crypto_id);
CREATE INDEX idx_alerts_log_timestamp ON alerts_log(timestamp DESC);

-- TABLE 4: user_preferences

-- User notification settings
CREATE TABLE user_preferences (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email_alerts_enabled BOOLEAN DEFAULT TRUE,
    daily_summary_enabled BOOLEAN DEFAULT TRUE,
    watchlist_alerts_enabled BOOLEAN DEFAULT TRUE,
    price_alerts_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ROW LEVEL SECURITY (RLS) POLICIES

-- Enable RLS on all tables
ALTER TABLE popular_cryptos ENABLE ROW LEVEL SECURITY;
ALTER TABLE watchlist ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;

-- popular_cryptos policies (public read, service role write)
CREATE POLICY "Anyone can read popular_cryptos"
    ON popular_cryptos FOR SELECT
    USING (true);

CREATE POLICY "Service role can insert popular_cryptos"
    ON popular_cryptos FOR INSERT
    WITH CHECK (auth.jwt()->>'role' = 'service_role');

CREATE POLICY "Service role can update popular_cryptos"
    ON popular_cryptos FOR UPDATE
    USING (auth.jwt()->>'role' = 'service_role');

CREATE POLICY "Service role can delete popular_cryptos"
    ON popular_cryptos FOR DELETE
    USING (auth.jwt()->>'role' = 'service_role');

-- watchlist policies (users manage their own)
CREATE POLICY "Users can view own watchlist"
    ON watchlist FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own watchlist"
    ON watchlist FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own watchlist"
    ON watchlist FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own watchlist"
    ON watchlist FOR DELETE
    USING (auth.uid() = user_id);

-- alerts_log policies (users view their own)
CREATE POLICY "Users can view own alerts"
    ON alerts_log FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Service role can insert alerts"
    ON alerts_log FOR INSERT
    WITH CHECK (auth.jwt()->>'role' = 'service_role');

-- user_preferences policies
CREATE POLICY "Users can view own preferences"
    ON user_preferences FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can update own preferences"
    ON user_preferences FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own preferences"
    ON user_preferences FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- HELPER FUNCTIONS

-- Check if cache is stale (older than 5 minutes)
CREATE OR REPLACE FUNCTION is_popular_cryptos_cache_stale()
RETURNS BOOLEAN AS $$
    SELECT COALESCE(
        (SELECT MAX(updated_at) < NOW() - INTERVAL '5 minutes' 
         FROM popular_cryptos),
        true  -- Return true if table is empty
    );
$$ LANGUAGE SQL STABLE;

-- Get cached crypto info by API ID
CREATE OR REPLACE FUNCTION get_cached_crypto_info(p_api_crypto_id INTEGER)
RETURNS TABLE(
    api_id INTEGER,
    symbol VARCHAR(10),
    name VARCHAR(100),
    logo_url TEXT,
    price NUMERIC(20,8),
    market_cap NUMERIC(20,2),
    volume_24h NUMERIC(20,2),
    change_24h NUMERIC(10,4),
    price_updated_at TIMESTAMP
) AS $$
    SELECT 
        api_id,
        symbol,
        name,
        logo_url,
        price,
        market_cap,
        volume_24h,
        change_24h,
        price_updated_at
    FROM popular_cryptos 
    WHERE api_id = p_api_crypto_id;
$$ LANGUAGE SQL STABLE;

-- Auto-update watchlist cache when popular_cryptos changes
CREATE OR REPLACE FUNCTION update_watchlist_cache_from_popular()
RETURNS TRIGGER AS $$
BEGIN
    -- Update all watchlist entries for this crypto with latest cached data
    UPDATE watchlist
    SET 
        symbol = NEW.symbol,
        name = NEW.name,
        logo_url = NEW.logo_url
    WHERE api_crypto_id = NEW.api_id;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to keep watchlist cache in sync
DROP TRIGGER IF EXISTS trigger_update_watchlist_cache ON popular_cryptos;
CREATE TRIGGER trigger_update_watchlist_cache
    AFTER INSERT OR UPDATE ON popular_cryptos
    FOR EACH ROW
    EXECUTE FUNCTION update_watchlist_cache_from_popular();

-- DOCUMENTATION COMMENTS

COMMENT ON TABLE popular_cryptos IS 'Caches top 100 cryptocurrencies from CoinDesk API, refreshed every 5 minutes';
COMMENT ON TABLE watchlist IS 'User watchlists with cached crypto info for fast display';
COMMENT ON TABLE alerts_log IS 'History of triggered price alerts';
COMMENT ON TABLE user_preferences IS 'User notification preferences';
COMMENT ON COLUMN user_preferences.watchlist_alerts_enabled IS 'Send emails when watchlist items are added/removed';
COMMENT ON COLUMN user_preferences.price_alerts_enabled IS 'Send emails when price alerts trigger';

COMMENT ON COLUMN popular_cryptos.api_id IS 'CoinDesk API unique identifier (e.g., 1=Bitcoin, 2=Ethereum)';
COMMENT ON COLUMN popular_cryptos.price_updated_at IS 'Timestamp from CoinDesk API when price was last updated';
COMMENT ON COLUMN popular_cryptos.cached_at IS 'When this record was first cached in database';
COMMENT ON COLUMN popular_cryptos.updated_at IS 'When this record was last refreshed from API';

COMMENT ON COLUMN watchlist.api_crypto_id IS 'CoinDesk API ID - used to fetch live data';
COMMENT ON COLUMN watchlist.symbol IS 'Cached symbol for display (auto-updated from popular_cryptos)';
COMMENT ON COLUMN watchlist.name IS 'Cached name for display (auto-updated from popular_cryptos)';
COMMENT ON COLUMN watchlist.logo_url IS 'Cached logo for display (auto-updated from popular_cryptos)';
COMMENT ON COLUMN watchlist.alert_percent IS 'Alert threshold percentage (e.g., 5.0 = alert on ±5% change)';