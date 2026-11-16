// Fixture source. This comment must not appear in public evidence.
namespace features {
#if BUILDFLAG(IS_WIN)
BASE_FEATURE(kLinked, "Linked", base::FEATURE_ENABLED_BY_DEFAULT);
#elif BUILDFLAG(IS_MAC)
BASE_FEATURE(kLinked, "Linked", base::FEATURE_DISABLED_BY_DEFAULT);
#else
BASE_FEATURE(kOtherPlatform, "OtherPlatform", base::FEATURE_DISABLED_BY_DEFAULT);
#endif
BASE_FEATURE(kHidden, "Hidden", base::FEATURE_DISABLED_BY_DEFAULT);
BASE_FEATURE(kModern, base::FEATURE_ENABLED_BY_DEFAULT);
const base::Feature kDirect{"Direct", base::FEATURE_ENABLED_BY_DEFAULT};
const base::Feature& kAlias = kHidden;
BASE_DECLARE_FEATURE(kDeclared);
extern const base::Feature kExtern;
BASE_FEATURE(kUnresolved, WRAPPED_NAME("Dynamic"), PICK_DEFAULT());
}
namespace switches {
const char kFirst[] = "first-switch";
constexpr char kSecond[] = "second-switch";
const wchar_t kWide[] = L"wide-switch";
const char kAlias[] = kFirst;
const char kUnknown[] = MAKE_SWITCH();
extern const char kDeclaration[];
}
