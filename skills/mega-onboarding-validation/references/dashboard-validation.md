# Dashboard validation

## Data-backed checks

Verify the selected country against aggregate tables:

- country metadata and currency;
- available spending years;
- total approved and executed values;
- functional and economic categories;
- domestic/foreign funding split where available;
- central/decentralized spending;
- per-capita values and population year policy;
- poverty/HDI/outcome years and no-data handling.

## Map checks

- boundary count matches the admin contract;
- all geometries are valid and render;
- mapped data names are a subset of boundary names;
- unexpected unmatched names equal zero;
- accepted target units without values render as no-data;
- legends exclude no-data from numeric min/max;
- disputed-boundary layers remain correct;
- map center and zoom show the whole country;
- spending, poverty, and outcome maps share the intended harmonization.

## UI and narrative checks

- country selector and year slider behave across sparse years;
- empty states distinguish unavailable data from zero;
- source metadata identifies the correct source and coverage;
- narratives use the correct periods, units, and signs;
- translations are present for every supported language and grammar metadata remains valid;
- no country-specific branch breaks another country's views.

## Cache and deployment

Use the application's authorized cache invalidation route after upstream data changes. Confirm a fresh query returns the new country, then verify subsequent cached reads. Never delete broad cache directories or bypass authentication as a substitute for the supported endpoint.
