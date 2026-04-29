population_hands.* — hand histories игроков / population.
gto_hands.* — hand histories ботов / GTO.

stat_catalog.json — список статистик для расчёта.

Поля stat_catalog:
- contextFilters — базовый контекст спота;
- opportunity — denominator;
- success — numerator;
- targetLine / targetSizeBucket — выбранная линия/размер для UI, не автоматический фильтр denominator.

Если часть полей сложно извлечь из HH за 4 часа — делай best-effort и опиши assumptions в diagnosis.md.