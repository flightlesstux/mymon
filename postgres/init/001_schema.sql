-- mymon schema. Every table has a PRIMARY KEY so the collector can upsert idempotently.

CREATE TABLE city (
    city         TEXT PRIMARY KEY,
    country_iso2 TEXT NOT NULL,
    lat          DOUBLE PRECISION NOT NULL,
    lon          DOUBLE PRECISION NOT NULL,
    tz           TEXT NOT NULL
);

CREATE TABLE country_centroid (
    iso3 TEXT PRIMARY KEY,
    iso2 TEXT NOT NULL,
    name TEXT NOT NULL,
    lat  DOUBLE PRECISION NOT NULL,
    lon  DOUBLE PRECISION NOT NULL
);

CREATE TABLE weather_current (
    ts            TIMESTAMPTZ NOT NULL,
    city          TEXT NOT NULL,
    temp_c        NUMERIC,
    feels_like_c  NUMERIC,
    humidity      NUMERIC,
    wind_kph      NUMERIC,
    wind_dir      NUMERIC,
    pressure_hpa  NUMERIC,
    precip_mm     NUMERIC,
    cloud_pct     NUMERIC,
    weather_code  INTEGER,
    uv            NUMERIC,
    aqi_eu        NUMERIC,
    pm2_5         NUMERIC,
    pm10          NUMERIC,
    PRIMARY KEY (ts, city)
);
CREATE INDEX weather_current_city_ts ON weather_current (city, ts DESC);

CREATE TABLE weather_daily (
    day          DATE NOT NULL,
    city         TEXT NOT NULL,
    tmin_c       NUMERIC,
    tmax_c       NUMERIC,
    precip_mm    NUMERIC,
    wind_max_kph NUMERIC,
    weather_code INTEGER,
    PRIMARY KEY (day, city)
);

CREATE TABLE weather_forecast (
    city         TEXT NOT NULL,
    day          DATE NOT NULL,
    fetched_at   TIMESTAMPTZ NOT NULL,
    tmin_c       NUMERIC,
    tmax_c       NUMERIC,
    precip_mm    NUMERIC,
    precip_prob  NUMERIC,
    weather_code INTEGER,
    PRIMARY KEY (city, day)
);

CREATE TABLE fx_rate (
    ts     TIMESTAMPTZ NOT NULL,
    base   TEXT NOT NULL,
    quote  TEXT NOT NULL,
    rate   NUMERIC NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (ts, base, quote, source)
);
CREATE INDEX fx_rate_pair_ts ON fx_rate (base, quote, source, ts DESC);

CREATE TABLE crypto_tick (
    ts             TIMESTAMPTZ NOT NULL,
    symbol         TEXT NOT NULL,
    price          NUMERIC NOT NULL,
    volume_24h     NUMERIC,
    change_24h_pct NUMERIC,
    PRIMARY KEY (ts, symbol)
);
CREATE INDEX crypto_tick_symbol_ts ON crypto_tick (symbol, ts DESC);

CREATE TABLE crypto_daily (
    day    DATE NOT NULL,
    symbol TEXT NOT NULL,
    open   NUMERIC,
    high   NUMERIC,
    low    NUMERIC,
    close  NUMERIC,
    volume NUMERIC,
    PRIMARY KEY (day, symbol)
);

CREATE TABLE reserves (
    period_date  DATE NOT NULL,
    country_iso3 TEXT NOT NULL,
    country      TEXT NOT NULL,
    metric       TEXT NOT NULL,   -- total | ex_gold | gold | gross_fx | net
    value_usd    NUMERIC,
    source       TEXT NOT NULL,
    PRIMARY KEY (period_date, country_iso3, metric, source)
);
CREATE INDEX reserves_country_metric ON reserves (country_iso3, metric, period_date DESC);

CREATE TABLE earthquake (
    id       TEXT PRIMARY KEY,
    ts       TIMESTAMPTZ NOT NULL,
    lat      DOUBLE PRECISION NOT NULL,
    lon      DOUBLE PRECISION NOT NULL,
    depth_km NUMERIC,
    mag      NUMERIC,
    place    TEXT,
    source   TEXT NOT NULL
);
CREATE INDEX earthquake_ts ON earthquake (ts DESC);

CREATE TABLE iss_position (
    ts           TIMESTAMPTZ PRIMARY KEY,
    lat          DOUBLE PRECISION NOT NULL,
    lon          DOUBLE PRECISION NOT NULL,
    altitude_km  NUMERIC,
    velocity_kmh NUMERIC
);

CREATE TABLE btc_network (
    ts               TIMESTAMPTZ PRIMARY KEY,
    block_height     BIGINT,
    hashrate_ehs     NUMERIC,
    difficulty       NUMERIC,
    fee_fast         NUMERIC,
    fee_half_hour    NUMERIC,
    fee_hour         NUMERIC,
    fee_economy      NUMERIC,
    mempool_tx_count INTEGER,
    mempool_vsize    BIGINT
);

CREATE TABLE space_weather (
    ts                 TIMESTAMPTZ PRIMARY KEY,
    kp                 NUMERIC,
    solar_wind_speed   NUMERIC,
    solar_wind_density NUMERIC,
    bz                 NUMERIC
);

CREATE TABLE co2_monthly (
    month     DATE PRIMARY KEY,
    ppm       NUMERIC,
    trend_ppm NUMERIC
);

CREATE TABLE fuel_price (
    period_date  DATE NOT NULL,
    country_iso2 TEXT NOT NULL,
    region       TEXT NOT NULL DEFAULT '',
    fuel_type    TEXT NOT NULL,   -- petrol95 | diesel | lpg
    price        NUMERIC NOT NULL,
    currency     TEXT NOT NULL,
    unit         TEXT NOT NULL,
    source       TEXT NOT NULL,
    PRIMARY KEY (period_date, country_iso2, region, fuel_type, source)
);
CREATE INDEX fuel_price_lookup ON fuel_price (country_iso2, fuel_type, period_date DESC);

CREATE TABLE commodity_price (
    period_date DATE NOT NULL,
    commodity   TEXT NOT NULL,
    price       NUMERIC,
    unit        TEXT,
    source      TEXT NOT NULL,
    PRIMARY KEY (period_date, commodity, source)
);
CREATE INDEX commodity_price_lookup ON commodity_price (commodity, source, period_date DESC);

CREATE TABLE stock_index (
    day    DATE NOT NULL,
    symbol TEXT NOT NULL,
    close  NUMERIC,
    PRIMARY KEY (day, symbol)
);

CREATE TABLE nl_us_stock (
    day      DATE NOT NULL,
    symbol   TEXT NOT NULL,
    name     TEXT,
    close    NUMERIC,
    volume   BIGINT,
    currency TEXT,
    source   TEXT NOT NULL,
    PRIMARY KEY (day, symbol, source)
);
CREATE INDEX nl_us_stock_lookup ON nl_us_stock (symbol, source, day DESC);

CREATE TABLE price_index (
    period_date  DATE NOT NULL,
    country_iso3 TEXT NOT NULL,
    indicator    TEXT NOT NULL,
    value        NUMERIC,
    unit         TEXT,
    source       TEXT NOT NULL,
    PRIMARY KEY (period_date, country_iso3, indicator, source)
);
CREATE INDEX price_index_lookup ON price_index (indicator, country_iso3, period_date DESC);

CREATE TABLE aircraft_state (
    ts       TIMESTAMPTZ NOT NULL,
    icao24   TEXT NOT NULL,
    callsign TEXT,
    country  TEXT,
    lat      DOUBLE PRECISION,
    lon      DOUBLE PRECISION,
    alt_m    NUMERIC,
    velocity NUMERIC,
    heading  NUMERIC,
    PRIMARY KEY (ts, icao24)
);

-- Sub-national regions (currently: the 12 Dutch provinces) for regional breakdowns that a
-- single country-level row in price_index can't represent (e.g. house prices differ a lot
-- by province). Mirrors the country_centroid pattern: a small lookup table joined against
-- a metric table at query time.
CREATE TABLE region (
    code    TEXT PRIMARY KEY,   -- e.g. CBS RegioS code 'PV27'
    country_iso3 TEXT NOT NULL,
    name    TEXT NOT NULL,
    lat     DOUBLE PRECISION NOT NULL,
    lon     DOUBLE PRECISION NOT NULL
);

CREATE TABLE region_metric (
    period_date DATE NOT NULL,
    region_code TEXT NOT NULL,
    indicator   TEXT NOT NULL,
    value       NUMERIC,
    unit        TEXT,
    source      TEXT NOT NULL,
    PRIMARY KEY (period_date, region_code, indicator, source)
);
CREATE INDEX region_metric_lookup ON region_metric (indicator, region_code, period_date DESC);

-- Seed: the 12 Dutch provinces, centroid-ish coordinates (provincial capital or similar).
INSERT INTO region (code, country_iso3, name, lat, lon) VALUES
    ('PV20', 'NLD', 'Groningen',      53.2194, 6.5665),
    ('PV21', 'NLD', 'Fryslân',        53.1642, 5.7818),
    ('PV22', 'NLD', 'Drenthe',        52.7981, 6.6528),
    ('PV23', 'NLD', 'Overijssel',     52.4988, 6.0937),
    ('PV24', 'NLD', 'Flevoland',      52.5185, 5.4714),
    ('PV25', 'NLD', 'Gelderland',     52.0452, 5.8717),
    ('PV26', 'NLD', 'Utrecht',        52.0907, 5.1214),
    ('PV27', 'NLD', 'Noord-Holland',  52.3874, 4.6462),
    ('PV28', 'NLD', 'Zuid-Holland',   52.0705, 4.3007),
    ('PV29', 'NLD', 'Zeeland',        51.4988, 3.6136),
    ('PV30', 'NLD', 'Noord-Brabant',  51.6978, 5.3037),
    ('PV31', 'NLD', 'Limburg',        50.8514, 5.6910);

CREATE TABLE collector_run (
    id          BIGSERIAL PRIMARY KEY,
    source      TEXT NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL,
    ok          BOOLEAN NOT NULL,
    rows        INTEGER NOT NULL DEFAULT 0,
    error       TEXT
);
CREATE INDEX collector_run_source_ts ON collector_run (source, started_at DESC);

-- Seed: cities tracked by the weather source.
INSERT INTO city (city, country_iso2, lat, lon, tz) VALUES
    ('Istanbul',      'TR', 41.0082,  28.9784,  'Europe/Istanbul'),
    ('Ankara',        'TR', 39.9334,  32.8597,  'Europe/Istanbul'),
    ('London',        'GB', 51.5074,  -0.1278,  'Europe/London'),
    ('Paris',         'FR', 48.8566,   2.3522,  'Europe/Paris'),
    ('Berlin',        'DE', 52.5200,  13.4050,  'Europe/Berlin'),
    ('Amsterdam',     'NL', 52.3676,   4.9041,  'Europe/Amsterdam'),
    ('Rotterdam',     'NL', 51.9244,   4.4777,  'Europe/Amsterdam'),
    ('The Hague',     'NL', 52.0705,   4.3007,  'Europe/Amsterdam'),
    ('Utrecht',       'NL', 52.0907,   5.1214,  'Europe/Amsterdam'),
    ('Eindhoven',     'NL', 51.4416,   5.4697,  'Europe/Amsterdam'),
    ('Madrid',        'ES', 40.4168,  -3.7038,  'Europe/Madrid'),
    ('Rome',          'IT', 41.9028,  12.4964,  'Europe/Rome'),
    ('Moscow',        'RU', 55.7558,  37.6173,  'Europe/Moscow'),
    ('Dubai',         'AE', 25.2048,  55.2708,  'Asia/Dubai'),
    ('Cairo',         'EG', 30.0444,  31.2357,  'Africa/Cairo'),
    ('Mumbai',        'IN', 19.0760,  72.8777,  'Asia/Kolkata'),
    ('Singapore',     'SG',  1.3521, 103.8198,  'Asia/Singapore'),
    ('Beijing',       'CN', 39.9042, 116.4074,  'Asia/Shanghai'),
    ('Tokyo',         'JP', 35.6762, 139.6503,  'Asia/Tokyo'),
    ('Sydney',        'AU', -33.8688, 151.2093, 'Australia/Sydney'),
    ('New York',      'US', 40.7128, -74.0060,  'America/New_York'),
    ('San Francisco', 'US', 37.7749, -122.4194, 'America/Los_Angeles'),
    ('Los Angeles',   'US', 34.0522, -118.2437, 'America/Los_Angeles'),
    ('Mexico City',   'MX', 19.4326, -99.1332,  'America/Mexico_City'),
    ('São Paulo',     'BR', -23.5505, -46.6333, 'America/Sao_Paulo');

-- Seed: country centroids for geomap marker layers (World Bank / IMF style iso3).
INSERT INTO country_centroid (iso3, iso2, name, lat, lon) VALUES
('AFG','AF','Afghanistan',33.94,67.71),('ALB','AL','Albania',41.15,20.17),('DZA','DZ','Algeria',28.03,1.66),
('AGO','AO','Angola',-11.20,17.87),('ARG','AR','Argentina',-38.42,-63.62),('ARM','AM','Armenia',40.07,45.04),
('AUS','AU','Australia',-25.27,133.78),('AUT','AT','Austria',47.52,14.55),('AZE','AZ','Azerbaijan',40.14,47.58),
('BHS','BS','Bahamas',25.03,-77.40),('BHR','BH','Bahrain',25.93,50.64),('BGD','BD','Bangladesh',23.68,90.36),
('BLR','BY','Belarus',53.71,27.95),('BEL','BE','Belgium',50.50,4.47),('BEN','BJ','Benin',9.31,2.32),
('BTN','BT','Bhutan',27.51,90.43),('BOL','BO','Bolivia',-16.29,-63.59),('BIH','BA','Bosnia and Herzegovina',43.92,17.68),
('BWA','BW','Botswana',-22.33,24.68),('BRA','BR','Brazil',-14.24,-51.93),('BRN','BN','Brunei',4.54,114.73),
('BGR','BG','Bulgaria',42.73,25.49),('BFA','BF','Burkina Faso',12.24,-1.56),('BDI','BI','Burundi',-3.37,29.92),
('KHM','KH','Cambodia',12.57,104.99),('CMR','CM','Cameroon',7.37,12.35),('CAN','CA','Canada',56.13,-106.35),
('CAF','CF','Central African Republic',6.61,20.94),('TCD','TD','Chad',15.45,18.73),('CHL','CL','Chile',-35.68,-71.54),
('CHN','CN','China',35.86,104.20),('COL','CO','Colombia',4.57,-74.30),('COD','CD','Congo, Dem. Rep.',-4.04,21.76),
('COG','CG','Congo, Rep.',-0.23,15.83),('CRI','CR','Costa Rica',9.75,-83.75),('CIV','CI','Cote d''Ivoire',7.54,-5.55),
('HRV','HR','Croatia',45.10,15.20),('CUB','CU','Cuba',21.52,-77.78),('CYP','CY','Cyprus',35.13,33.43),
('CZE','CZ','Czechia',49.82,15.47),('DNK','DK','Denmark',56.26,9.50),('DOM','DO','Dominican Republic',18.74,-70.16),
('ECU','EC','Ecuador',-1.83,-78.18),('EGY','EG','Egypt',26.82,30.80),('SLV','SV','El Salvador',13.79,-88.90),
('EST','EE','Estonia',58.60,25.01),('ETH','ET','Ethiopia',9.15,40.49),('FIN','FI','Finland',61.92,25.75),
('FRA','FR','France',46.23,2.21),('GAB','GA','Gabon',-0.80,11.61),('GEO','GE','Georgia',42.32,43.36),
('DEU','DE','Germany',51.17,10.45),('GHA','GH','Ghana',7.95,-1.02),('GRC','GR','Greece',39.07,21.82),
('GTM','GT','Guatemala',15.78,-90.23),('GIN','GN','Guinea',9.95,-9.70),('HTI','HT','Haiti',18.97,-72.29),
('HND','HN','Honduras',15.20,-86.24),('HKG','HK','Hong Kong SAR, China',22.40,114.11),('HUN','HU','Hungary',47.16,19.50),
('ISL','IS','Iceland',64.96,-19.02),('IND','IN','India',20.59,78.96),('IDN','ID','Indonesia',-0.79,113.92),
('IRN','IR','Iran',32.43,53.69),('IRQ','IQ','Iraq',33.22,43.68),('IRL','IE','Ireland',53.41,-8.24),
('ISR','IL','Israel',31.05,34.85),('ITA','IT','Italy',41.87,12.57),('JAM','JM','Jamaica',18.11,-77.30),
('JPN','JP','Japan',36.20,138.25),('JOR','JO','Jordan',30.59,36.24),('KAZ','KZ','Kazakhstan',48.02,66.92),
('KEN','KE','Kenya',-0.02,37.91),('KOR','KR','Korea, Rep.',35.91,127.77),('KWT','KW','Kuwait',29.31,47.48),
('KGZ','KG','Kyrgyz Republic',41.20,74.77),('LAO','LA','Lao PDR',19.86,102.50),('LVA','LV','Latvia',56.88,24.60),
('LBN','LB','Lebanon',33.85,35.86),('LBY','LY','Libya',26.34,17.23),('LTU','LT','Lithuania',55.17,23.88),
('LUX','LU','Luxembourg',49.82,6.13),('MDG','MG','Madagascar',-18.77,46.87),('MWI','MW','Malawi',-13.25,34.30),
('MYS','MY','Malaysia',4.21,101.98),('MLI','ML','Mali',17.57,-4.00),('MLT','MT','Malta',35.94,14.38),
('MUS','MU','Mauritius',-20.35,57.55),('MEX','MX','Mexico',23.63,-102.55),('MDA','MD','Moldova',47.41,28.37),
('MNG','MN','Mongolia',46.86,103.85),('MNE','ME','Montenegro',42.71,19.37),('MAR','MA','Morocco',31.79,-7.09),
('MOZ','MZ','Mozambique',-18.67,35.53),('MMR','MM','Myanmar',21.91,95.96),('NAM','NA','Namibia',-22.96,18.49),
('NPL','NP','Nepal',28.39,84.12),('NLD','NL','Netherlands',52.13,5.29),('NZL','NZ','New Zealand',-40.90,174.89),
('NIC','NI','Nicaragua',12.87,-85.21),('NER','NE','Niger',17.61,8.08),('NGA','NG','Nigeria',9.08,8.68),
('MKD','MK','North Macedonia',41.61,21.75),('NOR','NO','Norway',60.47,8.47),('OMN','OM','Oman',21.51,55.92),
('PAK','PK','Pakistan',30.38,69.35),('PAN','PA','Panama',8.54,-80.78),('PNG','PG','Papua New Guinea',-6.31,143.96),
('PRY','PY','Paraguay',-23.44,-58.44),('PER','PE','Peru',-9.19,-75.02),('PHL','PH','Philippines',12.88,121.77),
('POL','PL','Poland',51.92,19.15),('PRT','PT','Portugal',39.40,-8.22),('QAT','QA','Qatar',25.35,51.18),
('ROU','RO','Romania',45.94,24.97),('RUS','RU','Russian Federation',61.52,105.32),('RWA','RW','Rwanda',-1.94,29.87),
('SAU','SA','Saudi Arabia',23.89,45.08),('SEN','SN','Senegal',14.50,-14.45),('SRB','RS','Serbia',44.02,21.01),
('SGP','SG','Singapore',1.35,103.82),('SVK','SK','Slovak Republic',48.67,19.70),('SVN','SI','Slovenia',46.15,14.99),
('SOM','SO','Somalia',5.15,46.20),('ZAF','ZA','South Africa',-30.56,22.94),('SSD','SS','South Sudan',6.88,31.31),
('ESP','ES','Spain',40.46,-3.75),('LKA','LK','Sri Lanka',7.87,80.77),('SDN','SD','Sudan',12.86,30.22),
('SWE','SE','Sweden',60.13,18.64),('CHE','CH','Switzerland',46.82,8.23),('SYR','SY','Syria',34.80,38.10),
('TWN','TW','Taiwan',23.70,120.96),('TJK','TJ','Tajikistan',38.86,71.28),('TZA','TZ','Tanzania',-6.37,34.89),
('THA','TH','Thailand',15.87,100.99),('TGO','TG','Togo',8.62,0.82),('TTO','TT','Trinidad and Tobago',10.69,-61.22),
('TUN','TN','Tunisia',33.89,9.54),('TUR','TR','Turkiye',38.96,35.24),('TKM','TM','Turkmenistan',38.97,59.56),
('UGA','UG','Uganda',1.37,32.29),('UKR','UA','Ukraine',48.38,31.17),('ARE','AE','United Arab Emirates',23.42,53.85),
('GBR','GB','United Kingdom',55.38,-3.44),('USA','US','United States',37.09,-95.71),('URY','UY','Uruguay',-32.52,-55.77),
('UZB','UZ','Uzbekistan',41.38,64.59),('VEN','VE','Venezuela',6.42,-66.59),('VNM','VN','Viet Nam',14.06,108.28),
('YEM','YE','Yemen',15.55,48.52),('ZMB','ZM','Zambia',-13.13,27.85),('ZWE','ZW','Zimbabwe',-19.02,29.15),
('EMU','EU','Euro area',50.0,9.0),('WLD','WW','World',0.0,0.0);

-- Dutch seaports (NL: Ports & Shipping) — mirrors the region/region_metric pattern above,
-- keyed by CBS's NederlandseZeehavens codes instead of provinces.
CREATE TABLE port (
    code    TEXT PRIMARY KEY,   -- CBS NederlandseZeehavens code, e.g. 'A041797'
    country_iso3 TEXT NOT NULL,
    name    TEXT NOT NULL,
    lat     DOUBLE PRECISION NOT NULL,
    lon     DOUBLE PRECISION NOT NULL
);

CREATE TABLE port_metric (
    period_date DATE NOT NULL,
    port_code   TEXT NOT NULL,
    indicator   TEXT NOT NULL,
    value       NUMERIC,
    unit        TEXT,
    source      TEXT NOT NULL,
    PRIMARY KEY (period_date, port_code, indicator, source)
);
CREATE INDEX port_metric_lookup ON port_metric (indicator, port_code, period_date DESC);

INSERT INTO port (code, country_iso3, name, lat, lon) VALUES
    ('A041797', 'NLD', 'Rotterdam',        51.9481, 4.1425),
    ('A041794', 'NLD', 'Amsterdam',        52.4084, 4.8523),
    ('A041795', 'NLD', 'Groningen Seaports', 53.4478, 6.8397),
    ('A041798', 'NLD', 'Zeeland Seaports', 51.4494, 3.7250);

-- Global electricity grid data (Denmark's Energi Data Service, UK's Carbon Intensity
-- API) — live/near-live snapshots, not backfillable, hence ts (not period_date) and a
-- retention policy (see retention.py) instead of unbounded history like price_index.
CREATE TABLE energy_grid (
    ts        TIMESTAMPTZ NOT NULL,
    region    TEXT NOT NULL,   -- e.g. 'DK1', 'DK2', 'GB'
    indicator TEXT NOT NULL,
    value     NUMERIC,
    unit      TEXT,
    source    TEXT NOT NULL,
    PRIMARY KEY (ts, region, indicator, source)
);
CREATE INDEX energy_grid_lookup ON energy_grid (indicator, region, ts DESC);

-- Global bike-share station snapshots (CityBikes) — live-only, no history endpoint
-- upstream, so this is a snapshot table with retention like aircraft_state/iss_position.
CREATE TABLE bike_network (
    ts           TIMESTAMPTZ NOT NULL,
    network_id   TEXT NOT NULL,
    city         TEXT NOT NULL,
    country      TEXT,
    lat          DOUBLE PRECISION,
    lon          DOUBLE PRECISION,
    free_bikes   INTEGER,
    empty_slots  INTEGER,
    stations     INTEGER,
    source       TEXT NOT NULL,
    PRIMARY KEY (ts, network_id, source)
);
CREATE INDEX bike_network_lookup ON bike_network (network_id, ts DESC);

-- Space weather gets three more live columns from a second source module
-- (space_monitor.py) — solar X-ray flux/flare class (NOAA SWPC) and active satellite
-- count (Celestrak) — sharing this table with the existing kp/solar-wind columns rather
-- than a new one, since it's the same "what's happening in near-Earth space right now"
-- concept. upsert() only ever writes the columns present in a given row, so the two
-- source modules don't clobber each other's columns even when their ts values differ.
ALTER TABLE space_weather ADD COLUMN IF NOT EXISTS xray_flux NUMERIC;
ALTER TABLE space_weather ADD COLUMN IF NOT EXISTS xray_flare_class TEXT;
ALTER TABLE space_weather ADD COLUMN IF NOT EXISTS satellites_active INTEGER;

-- NASA EONET natural events (volcanoes, storms, sea/lake ice, floods, etc. —
-- deliberately excludes wildfires, which run into the thousands of small local fires
-- and would swamp everything else). Live snapshot, not backfillable; see retention.py.
CREATE TABLE natural_event (
    id              TEXT PRIMARY KEY,   -- EONET event id, e.g. 'EONET_24184'
    title           TEXT NOT NULL,
    category        TEXT NOT NULL,
    lat             DOUBLE PRECISION,
    lon             DOUBLE PRECISION,
    event_date      TIMESTAMPTZ,        -- most recent known position/observation time
    magnitude_value NUMERIC,
    magnitude_unit  TEXT,
    source          TEXT NOT NULL
);
CREATE INDEX natural_event_category ON natural_event (category, event_date DESC);

-- The Space Devs' Launch Library 2: upcoming + recently-flown orbital launches.
CREATE TABLE space_launch (
    id       TEXT PRIMARY KEY,
    name     TEXT NOT NULL,
    status   TEXT,
    provider TEXT,
    rocket   TEXT,
    net      TIMESTAMPTZ,               -- scheduled/actual liftoff time
    pad_name TEXT,
    lat      DOUBLE PRECISION,
    lon      DOUBLE PRECISION,
    country  TEXT,
    orbit    TEXT,
    source   TEXT NOT NULL
);
CREATE INDEX space_launch_net ON space_launch (net DESC);

-- Open Notify: who's currently in space. Small live roster; see retention.py — a short
-- retention window on ts self-cleans anyone who's landed since the last fetch.
CREATE TABLE astronaut (
    name   TEXT NOT NULL,
    craft  TEXT,
    ts     TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (name, source)
);
