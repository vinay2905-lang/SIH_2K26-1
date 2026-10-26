import { createContext, ReactNode, useContext, useState } from "react";

type Lang = "en" | "hi";

// Hindi labels for navigation, the institution portal and statuses. Untranslated strings fall back to English.
const HI: Record<string, string> = {
  "Dashboard": "डैशबोर्ड",
  "Scrutiny queue": "जाँच कतार",
  "Applications": "आवेदन",
  "Verification": "सत्यापन",
  "Rulebook": "नियम पुस्तिका",
  "Audit trail": "ऑडिट ट्रेल",
  "Alerts": "सूचनाएँ",
  "My applications": "मेरे आवेदन",
  "Sign out": "साइन आउट",
  "Sign in": "साइन इन करें",
  "Username": "उपयोगकर्ता नाम",
  "Password": "पासवर्ड",
  "Documents and pre-check": "दस्तावेज़ और पूर्व-जाँच",
  "Application form": "आवेदन प्रपत्र",
  "Deficiency letters": "कमी पत्र",
  "Submit application": "आवेदन जमा करें",
  "Upload": "अपलोड करें",
  "Replace": "बदलें",
  "Use sample": "नमूना फ़ाइल",
  "Start a new application": "नया आवेदन शुरू करें",
  "Required documents": "आवश्यक दस्तावेज़",
  "What we found": "जाँच का परिणाम",
  "Before you submit": "जमा करने से पहले",
  "Save form": "प्रपत्र सहेजें",
  "Open": "खोलें",
  "Reply": "उत्तर दें",
  "Pre-check results": "पूर्व-जाँच के परिणाम",
  "The pre-check is advisory. AICTE officials take the final decision on every application.":
    "पूर्व-जाँच केवल सलाह है। हर आवेदन पर अंतिम निर्णय एआईसीटीई अधिकारी लेते हैं।",
  "Verified": "सत्यापित",
  "Mismatch": "बेमेल",
  "Expired": "समाप्त",
  "Pending": "लंबित",
  "Source unavailable": "स्रोत उपलब्ध नहीं",
  "Manual review": "मैन्युअल जाँच",
  "Not uploaded": "अपलोड नहीं",
  "Reading…": "पढ़ा जा रहा है…",
  "Uploaded": "अपलोड हुआ",
  "Critical": "गंभीर",
  "High": "उच्च",
  "Warning": "चेतावनी",
  "Info": "सूचना",
};

const LangContext = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: "en", setLang: () => {} });

function initial(): Lang {
  try {
    return localStorage.getItem("pramaan.lang") === "hi" ? "hi" : "en";
  } catch {
    return "en";
  }
}

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, set] = useState<Lang>(initial);
  const setLang = (l: Lang) => {
    set(l);
    try {
      localStorage.setItem("pramaan.lang", l);
    } catch {
      /* ignore */
    }
    document.documentElement.lang = l;
  };
  return <LangContext.Provider value={{ lang, setLang }}>{children}</LangContext.Provider>;
}

export function useLang() {
  return useContext(LangContext);
}

export function useT() {
  const { lang } = useContext(LangContext);
  return (s: string) => (lang === "hi" ? HI[s] || s : s);
}
