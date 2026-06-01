import { SUPPORTED_LOCALES, type Locale } from "../lib/i18n/types";
import { useI18n, useT } from "../lib/i18n/context";

/**
 * CS | EN language switcher.
 * Renders as two pill buttons with the active locale highlighted.
 * Reads and writes locale via the I18nContext.
 */
export function LangSwitcher() {
  const { locale, setLocale } = useI18n();
  const t = useT();

  return (
    <div
      role="group"
      aria-label={t("lang.switcher.aria")}
      className="flex items-center rounded-md border border-glass overflow-hidden"
    >
      {(SUPPORTED_LOCALES as Locale[]).map((lang, idx) => (
        <button
          key={lang}
          type="button"
          onClick={() => setLocale(lang)}
          className={[
            "px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest transition",
            idx > 0 ? "border-l border-glass" : "",
            locale === lang
              ? "bg-cobweb-500/20 text-cobweb-300"
              : "text-neutral-500 hover:bg-white/[0.04] hover:text-neutral-300",
          ]
            .filter(Boolean)
            .join(" ")}
          aria-pressed={locale === lang}
        >
          {t(`lang.${lang}` as Parameters<typeof t>[0])}
        </button>
      ))}
    </div>
  );
}
