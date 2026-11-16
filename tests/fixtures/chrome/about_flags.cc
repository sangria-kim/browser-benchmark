namespace flag_descriptions {
const char kDemoName[] = "Demo name";
const char kDemoDescription[] = "Demo description";
}
namespace {
const FeatureEntry::Choice kChoices[] = {
    {"Default", "", ""},
    {"First", switches::kFirst, "one"},
    {"Second", switches::kSecond, "two"},
};
const FeatureEntry::FeatureParam kParams[] = {{"mode", "fast"}, {"count", "2"}};
const FeatureEntry::FeatureVariation kVariations[] = {{"Fast", kParams, nullptr}};
const FeatureEntry kFeatureEntries[] = {
#if BUILDFLAG(IS_WIN)
    {"demo", flag_descriptions::kDemoName, flag_descriptions::kDemoDescription,
     kOsWin, FEATURE_WITH_PARAMS_VALUE_TYPE(features::kHidden, kVariations, "Trial")},
#endif
    {"switch-demo", "Switch demo", "Switches", kOsAll, MULTI_VALUE_TYPE(kChoices)},
    {"old-demo", "Old demo", "Expired", kOsAll, FEATURE_VALUE_TYPE(features::kHidden)},
    {"never-demo", "Never demo", "Never", kOsAll, FEATURE_VALUE_TYPE(features::kHidden)},
    {"unknown-demo", "Unknown", "Unknown", kOsAll, FUTURE_VALUE_TYPE(features::kHidden)},
};
}
