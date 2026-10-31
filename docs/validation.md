# Wildfire Spread Model Empirical Validation

Empirical validation of the EmberRoute minimum travel-time simulation engine against real historical NASA FIRMS satellite observations and Open-Meteo meteorological reanalysis.

## Performance Comparison

| Event | Split | Grid | Future detections | Model recall | Baseline recall | Predicted area (ha) | Bearing error (deg) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Malawi_Border_Fire_-38_136 | train | 20x20 (1244m) | 39 | 0.718 | 0.718 | 41466.1 | 30.7 |
| Kruger_Region_Fire_-92_124 | train | 19x21 (1213m) | 17 | 1.000 | 1.000 | 55642.7 | 5.3 |
| Tanami_Bushfire_-84_515 | test | 19x21 (1207m) | 53 | 1.000 | 0.943 | 55324.6 | 73.1 |

## Calibrated Parameters

Optimal parameters selected via bounded grid search on the training events:
- `k_wind`: 0.1
- `midflame`: 0.3
- `ros_scale`: 2.0
- `lb_cap`: 8.0

## Validation Analysis & Comparison

- **Held-out Test Model Recall**: 100.0%
- **Held-out Test Baseline Recall**: 94.3%
- **Performance Margin**: +5.7% vs matched-area isotropic baseline.

## Limitations

An honest engineering assessment of current model and data limitations:
1. **Satellite Temporal Sparsity**: NASA VIIRS satellites pass over a given location only 1-2 times daily. Sensor observations lag physical spread fronts, capturing discrete snapshots rather than continuous fire perimeters.
2. **Recall vs IoU**: Satellite thermal detections provide point locations of flaming fronts without confirming unburned interior pockets or fuel discontinuities.
3. **Absence of Spotting and Suppression**: The model simulates surface rate-of-spread and does not currently model aerodynamic ember lofting (spotting fires) or human suppression actions (firebreaks, retardant drops).
4. **Sample Size**: Evaluated across 3 real historical fire clusters. Broader geographic calibration across differing bioclimatic zones is recommended for production deployment.

## Data Provenance

All validation inputs were retrieved from authoritative upstream repositories without mock or placeholder data:
### Malawi_Border_Fire_-38_136
- `https://firms.modaps.eosdis.nasa.gov/data/active_fire/suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_Global_7d.csv`
- `https://archive-api.open-meteo.com/v1/archive?latitude=-9.3664&longitude=34.1281&start_date=2026-10-25&end_date=2026-10-27&hourly=wind_speed_10m%2Cwind_direction_10m%2Cwind_gusts_10m%2Crelative_humidity_2m%2Ctemperature_2m&wind_speed_unit=ms&timezone=UTC`
- `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/12/[2434..2437]/[2153..2156].png`
- `https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_[S12E033]_Map.tif`
### Kruger_Region_Fire_-92_124
- `https://firms.modaps.eosdis.nasa.gov/data/active_fire/suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_Global_7d.csv`
- `https://archive-api.open-meteo.com/v1/archive?latitude=-22.9491&longitude=31.0928&start_date=2026-10-27&end_date=2026-10-29&hourly=wind_speed_10m%2Cwind_direction_10m%2Cwind_gusts_10m%2Crelative_humidity_2m%2Ctemperature_2m&wind_speed_unit=ms&timezone=UTC`
- `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/12/[2400..2403]/[2314..2318].png`
- `https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_[S24E030]_Map.tif`
### Tanami_Bushfire_-84_515
- `https://firms.modaps.eosdis.nasa.gov/data/active_fire/suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_Global_7d.csv`
- `https://archive-api.open-meteo.com/v1/archive?latitude=-20.9061&longitude=128.8748&start_date=2026-10-25&end_date=2026-10-27&hourly=wind_speed_10m%2Cwind_direction_10m%2Cwind_gusts_10m%2Crelative_humidity_2m%2Ctemperature_2m&wind_speed_unit=ms&timezone=UTC`
- `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/12/[3512..3515]/[2289..2292].png`
- `https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_[S21E126,S24E126]_Map.tif`