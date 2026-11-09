// Scan old notebook module: handles camera capture, file upload, image preview,
// scanning sweep animation, editable review table, and ledger confirmation.

export const SCAN_TRANSLATIONS = {
  'hi-en': {
    scanButton: 'Scan notebook',
    modalTitle: 'Scan old notebook',
    scanning: 'Scanning notebook...',
    safetyNote: 'Check names and amounts before adding.',
    thSelect: 'Select',
    thCustomer: 'Customer',
    thAmount: 'Amount (₹)',
    thType: 'Type',
    thNote: 'Note',
    newBadge: 'New',
    lowConfidence: 'Check',
    credit: 'Udhaar',
    payment: 'Jama',
    addAll: 'Add all selected',
    cancel: 'Cancel',
    successToast: (n) => `${n} entries added to ledger`,
    noRowsFound: 'No ledger entries found on this page. Please try a clearer photo.',
    errFileSize: 'File size exceeds 8 MB limit.',
    errFileType: 'Please select a valid image file (JPG, PNG, WEBP, or HEIC).',
    errGeneric: 'Could not process notebook image. Please try again.',
    emptySelection: 'Please select at least one entry to add.',
  },
  'hi-IN': {
    scanButton: 'बही-खाता स्कैन करें',
    modalTitle: 'पुराना बही-खाता स्कैन करें',
    scanning: 'खाता स्कैन हो रहा है...',
    safetyNote: 'जोड़ने से पहले नाम और रकम ज़रूर जांच लें।',
    thSelect: 'चुनें',
    thCustomer: 'ग्राहक',
    thAmount: 'रकम (₹)',
    thType: 'प्रकार',
    thNote: 'विवरण',
    newBadge: 'नया',
    lowConfidence: 'जांचें',
    credit: 'उधार',
    payment: 'जमा',
    addAll: 'चुने हुए जोड़ें',
    cancel: 'रद्द करें',
    successToast: (n) => `${n} प्रविष्टियां खाते में जोड़ दी गईं`,
    noRowsFound: 'इस पन्ने पर कोई प्रविष्टि नहीं मिली। कृपया साफ़ फोटो लें।',
    errFileSize: 'फ़ाइल का साइज़ 8 MB से अधिक है।',
    errFileType: 'कृपया सही फोटो फ़ाइल चुनें (JPG, PNG, WEBP, या HEIC)।',
    errGeneric: 'फोटो स्कैन नहीं हो सकी। कृपया पुनः प्रयास करें।',
    emptySelection: 'कृपया जोड़ने के लिए कम से कम एक प्रविष्टि चुनें।',
  },
  'mr-IN': {
    scanButton: 'वही स्कॅन करा',
    modalTitle: 'जुनी वही स्कॅन करा',
    scanning: 'वही स्कॅन होत आहे...',
    safetyNote: 'नोंद करण्यापूर्वी नावे आणि रक्कम तपासून घ्या.',
    thSelect: 'निवडा',
    thCustomer: 'ग्राहक',
    thAmount: 'रक्कम (₹)',
    thType: 'प्रकार',
    thNote: 'टीप',
    newBadge: 'नवीन',
    lowConfidence: 'तपासा',
    credit: 'उधार',
    payment: 'जमा',
    addAll: 'निवडलेले सर्व जोडा',
    cancel: 'रद्द करा',
    successToast: (n) => `${n} नोंदी खात्यात जोडल्या गेल्या`,
    noRowsFound: 'या पानावर कोणतीही नोंद आढळली नाही. कृपया स्पष्ट फोटो घ्या.',
    errFileSize: 'फाइल आकार 8 MB पेक्षा जास्त आहे.',
    errFileType: 'कृपया वैध फोटो फाइल निवडा (JPG, PNG, WEBP, किंवा HEIC).',
    errGeneric: 'फोटो स्कॅन करता आला नाही. कृपया पुन्हा प्रयत्न करा.',
    emptySelection: 'कृपया जोडण्यासाठी किमान एक नोंद निवडा.',
  },
  'gu-IN': {
    scanButton: 'ચોપડો સ્કેન કરો',
    modalTitle: 'જૂનો ચોપડો સ્કેન કરો',
    scanning: 'ચોપડો સ્કેન થઈ રહ્યો છે...',
    safetyNote: 'ઉમેરતા પહેલાં નામ અને રકમ ચકાસી લો.',
    thSelect: 'પસંદ કરો',
    thCustomer: 'ગ્રાહક',
    thAmount: 'રકમ (₹)',
    thType: 'પ્રકાર',
    thNote: 'નોંધ',
    newBadge: 'નવું',
    lowConfidence: 'ચકાસો',
    credit: 'ઉધાર',
    payment: 'જમા',
    addAll: 'પસંદ કરેલ બધું ઉમેરો',
    cancel: 'રદ કરો',
    successToast: (n) => `${n} એન્ટ્રીઓ ખાતામાં ઉમેરાઈ`,
    noRowsFound: 'કોઈ એન્ટ્રી મળી નથી. કૃપા કરીને સ્પષ્ટ ફોટો લો.',
    errFileSize: 'ફાઇલનું કદ 8 MB કરતાં વધુ છે.',
    errFileType: 'કૃપા કરીને માન્ય ફોટો ફાઇલ પસંદ કરો (JPG, PNG, WEBP, અથવા HEIC).',
    errGeneric: 'ફોટો સ્કેન થઈ શક્યો નથી. કૃપા કરીને ફરી પ્રયાસ કરો.',
    emptySelection: 'કૃપા કરીને ઉમેરવા માટે ઓછામાં ઓછી એક એન્ટ્રી પસંદ કરો.',
  },
  'ta-IN': {
    scanButton: 'நோட்டுப் புத்தகத்தை ஸ்கேன் செய்',
    modalTitle: 'பழைய நோட்டை ஸ்கேன் செய்',
    scanning: 'பக்கம் ஸ்கேன் செய்யப்படுகிறது...',
    safetyNote: 'சேர்ப்பதற்கு முன் பெயர்களையும் தொகையையும் சரிபார்க்கவும்.',
    thSelect: 'தேர்வு',
    thCustomer: 'வாடிக்கையாளர்',
    thAmount: 'தொகை (₹)',
    thType: 'வகை',
    thNote: 'குறிப்பு',
    newBadge: 'புதியது',
    lowConfidence: 'சரிபார்',
    credit: 'கடன்',
    payment: 'வரவு',
    addAll: 'தேர்ந்தெடுத்தவற்றைச் சேர்',
    cancel: 'ரத்து செய்',
    successToast: (n) => `${n} பதிவுகள் கணக்கில் சேர்க்கப்பட்டன`,
    noRowsFound: 'இந்தப் பக்கத்தில் பதிவுகள் எதுவும் கிடைக்கவில்லை. தெளிவான புகைப்படத்தை எடுக்கவும்.',
    errFileSize: 'கோப்பு அளவு 8 MB வரம்பை தாண்டியது.',
    errFileType: 'சரியான புகைப்பட கோப்பைத் தேர்ந்தெடுக்கவும் (JPG, PNG, WEBP, அல்லது HEIC).',
    errGeneric: 'புகைப்படத்தை ஸ்கேன் செய்ய முடியவில்லை. மீண்டும் முயற்சிக்கவும்.',
    emptySelection: 'சேர்ப்பதற்கு குறைந்தபட்சம் ஒரு பதிவைத் தேர்ந்தெடுக்கவும்.',
  },
  'te-IN': {
    scanButton: 'నోట్‌బుక్ స్కాన్ చేయండి',
    modalTitle: 'పాత ఖాతా పుస్తకాన్ని స్కాన్ చేయండి',
    scanning: 'పుస్తకం స్కాన్ అవుతోంది...',
    safetyNote: 'జోడించే ముందు పేర్లు మరియు మొత్తాలను తనిఖీ చేయండి.',
    thSelect: 'ఎంచుకోండి',
    thCustomer: 'ఖాతాదారు',
    thAmount: 'మొత్తం (₹)',
    thType: 'రకం',
    thNote: 'గమనిక',
    newBadge: 'కొత్తది',
    lowConfidence: 'తనిఖీ',
    credit: 'అప్పు',
    payment: 'జమ',
    addAll: 'ఎంచుకున్నవన్నీ జోడించు',
    cancel: 'రద్దు చేయి',
    successToast: (n) => `${n} ఎంట్రీలు లెడ్జర్‌లో చేర్చబడ్డాయి`,
    noRowsFound: 'ఈ పేజీలో ఎలాంటి ఎంట్రీలు కనుగొనబడలేదు. దయచేసి స్పష్టమైన ఫోటో తీయండి.',
    errFileSize: 'ఫైల్ పరిమాణం 8 MB కంటే ఎక్కువగా ఉంది.',
    errFileType: 'దయచేసి చెల్లుబాటు అయ్యే చిత్రాన్ని ఎంచుకోండి (JPG, PNG, WEBP, లేదా HEIC).',
    errGeneric: 'చిత్రాన్ని స్కాన్ చేయడం సాధ్యం కాలేదు. మళ్ళీ ప్రయత్నించండి.',
    emptySelection: 'దయచేసి జోడించడానికి కనీసం ఒక ఎంట్రీని ఎంచుకోండి.',
  },
  'bn-IN': {
    scanButton: 'খাতা স্ক্যান করুন',
    modalTitle: 'পুরোনো খাতা স্ক্যান করুন',
    scanning: 'খাতা স্ক্যান করা হচ্ছে...',
    safetyNote: 'যোগ করার আগে নাম এবং পরিমাণ যাচাই করে নিন।',
    thSelect: 'নির্বাচন',
    thCustomer: 'গ্রাহক',
    thAmount: 'পরিমাণ (₹)',
    thType: 'ধরন',
    thNote: 'নোট',
    newBadge: 'নতুন',
    lowConfidence: 'যাচাই',
    credit: 'ধার',
    payment: 'জমা',
    addAll: 'নির্বাচিত সব যোগ করুন',
    cancel: 'বাতিল করুন',
    successToast: (n) => `${n}টি এন্ট্রি খাতায় যোগ করা হয়েছে`,
    noRowsFound: 'এই পাতায় কোনো হিসাব পাওয়া যায়নি। স্পষ্ট ছবি তোলার চেষ্টা করুন।',
    errFileSize: 'ফাইলের আকার ৮ এমবি-র বেশি।',
    errFileType: 'সঠিক ছবির ফাইল বেছে নিন (JPG, PNG, WEBP বা HEIC)।',
    errGeneric: 'ছবি স্ক্যান করা যায়নি। অনুগ্রহ করে আবার চেষ্টা করুন।',
    emptySelection: 'অনুগ্রহ করে অন্তত একটি এন্ট্রি বেছে নিন।',
  },
  'kn-IN': {
    scanButton: 'ಪುಸ್ತಕ ಸ್ಕ್ಯಾನ್ ಮಾಡಿ',
    modalTitle: 'ಹಳೆಯ ಖಾತಾ ಪುಸ್ತಕ ಸ್ಕ್ಯಾನ್ ಮಾಡಿ',
    scanning: 'ಪುಸ್ತಕ ಸ್ಕ್ಯಾನ್ ಆಗುತ್ತಿದೆ...',
    safetyNote: 'ಸೇರಿಸುವ ಮೊದಲು ಹೆಸರು ಮತ್ತು ಮೊತ್ತವನ್ನು ಪರಿಶೀಲಿಸಿ.',
    thSelect: 'ಆಯ್ಕೆ',
    thCustomer: 'ಗ್ರಾಹಕ',
    thAmount: 'ಮೊತ್ತ (₹)',
    thType: 'ವಿಧ',
    thNote: 'ಟಿಪ್ಪಣಿ',
    newBadge: 'ಹೊಸದು',
    lowConfidence: 'ಪರಿಶೀಲಿಸಿ',
    credit: 'ಉದ್ದರಿ',
    payment: 'ಜಮೆ',
    addAll: 'ಆಯ್ಕೆಮಾಡಿದ್ದನ್ನು ಸೇರಿಸಿ',
    cancel: 'ರದ್ದುಮಾಡಿ',
    successToast: (n) => `${n} ನಮೂದುಗಳನ್ನು ಲೆಡ್ಜರ್‌ಗೆ ಸೇರಿಸಲಾಗಿದೆ`,
    noRowsFound: 'ಯಾವುದೇ ನಮೂದು ಕಂಡುಬಂದಿಲ್ಲ. ದಯವಿಟ್ಟು ಸ್ಪಷ್ಟ ಫೋಟೋ ತೆಗೆದುಕೊಳ್ಳಿ.',
    errFileSize: 'ಫೈಲ್ ಗಾತ್ರವು 8 MB ಮೀರಿದೆ.',
    errFileType: 'ದಯವಿಟ್ಟು ಮಾನ್ಯವಾದ ಚಿತ್ರ ಫೈಲ್ ಆಯ್ಕೆಮಾಡಿ (JPG, PNG, WEBP, ಅಥವಾ HEIC).',
    errGeneric: 'ಸ್ಕ್ಯಾನ್ ಮಾಡಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.',
    emptySelection: 'ದಯವಿಟ್ಟು ಸೇರಿಸಲು ಕನಿಷ್ಠ ಒಂದು ನಮೂದನ್ನು ಆಯ್ಕೆಮಾಡಿ.',
  },
  'ml-IN': {
    scanButton: 'നോട്ട്ബുക്ക് സ്കാൻ ചെയ്യുക',
    modalTitle: 'പഴയ നോട്ട്ബുക്ക് സ്കാൻ ചെയ്യുക',
    scanning: 'പേജ് സ്കാൻ ചെയ്യുന്നു...',
    safetyNote: 'ചേർക്കുന്നതിന് മുമ്പ് പേരും തുകയും പരിശോധിക്കുക.',
    thSelect: 'തിരഞ്ഞെടുക്കുക',
    thCustomer: 'ഉപഭോക്താവ്',
    thAmount: 'തുക (₹)',
    thType: 'ഇനം',
    thNote: 'കുറിപ്പ്',
    newBadge: 'പുതിയത്',
    lowConfidence: 'പരിശോധിക്കുക',
    credit: 'കടം',
    payment: 'വരവ്',
    addAll: 'തിരഞ്ഞെടുത്തവ ചേർക്കുക',
    cancel: 'റദ്ദാക്കുക',
    successToast: (n) => `${n} എൻട്രികൾ ലെഡ്ജറിൽ ചേർത്തു`,
    noRowsFound: 'എൻട്രികൾ ഒന്നും കണ്ടെത്താനായില്ല. വ്യക്തമായ ഫോട്ടോ എടുക്കുക.',
    errFileSize: 'ഫയൽ വലുപ്പം 8 MB-യിൽ കൂടുതലാണ്.',
    errFileType: 'ശരിയായ ഇമേജ് ഫയൽ തിരഞ്ഞെടുക്കുക (JPG, PNG, WEBP, അല്ലെങ്കിൽ HEIC).',
    errGeneric: 'സ്കാൻ ചെയ്യാനായില്ല. വീണ്ടും ശ്രമിക്കുക.',
    emptySelection: 'ചേർക്കുന്നതിനായി കുറഞ്ഞത് ഒരു എൻട്രിയെങ്കിലും തിരഞ്ഞെടുക്കുക.',
  },
  'pa-IN': {
    scanButton: 'ਵਹੀ ਸਕੈਨ ਕਰੋ',
    modalTitle: 'ਪੁਰਾਣੀ ਵਹੀ ਸਕੈਨ ਕਰੋ',
    scanning: 'ਸਕੈਨ ਕੀਤਾ ਜਾ ਰਿਹਾ ਹੈ...',
    safetyNote: 'ਜੋੜਨ ਤੋਂ ਪਹਿਲਾਂ ਨਾਮ ਅਤੇ ਰਕਮ ਦੀ ਜਾਂਚ ਕਰੋ।',
    thSelect: 'ਚੁਣੋ',
    thCustomer: 'ਗਾਹਕ',
    thAmount: 'ਰਕਮ (₹)',
    thType: 'ਕਿਸਮ',
    thNote: 'ਨੋਟ',
    newBadge: 'ਨਵਾਂ',
    lowConfidence: 'ਜਾਂਚੋ',
    credit: 'ਉਧਾਰ',
    payment: 'ਜਮ੍ਹਾਂ',
    addAll: 'ਚੁਣੇ ਹੋਏ ਸ਼ਾਮਲ ਕਰੋ',
    cancel: 'ਰੱਦ ਕਰੋ',
    successToast: (n) => `${n} ਐਂਟਰੀਆਂ ਖਾਤੇ ਵਿੱਚ ਜੋੜੀਆਂ ਗਈਆਂ`,
    noRowsFound: 'ਕੋਈ ਐਂਟਰੀ ਨਹੀਂ ਮਿਲੀ। ਕਿਰਪਾ ਕਰਕੇ ਸਾਫ਼ ਫੋਟੋ ਲਓ।',
    errFileSize: 'ਫ਼ਾਈਲ ਦਾ ਆਕਾਰ 8 MB ਤੋਂ ਵੱਧ ਹੈ।',
    errFileType: 'ਕਿਰਪਾ ਕਰਕੇ ਸਹੀ ਫੋਟੋ ਚੁਣੋ (JPG, PNG, WEBP, ਜਾਂ HEIC)।',
    errGeneric: 'ਸਕੈਨ ਨਹੀਂ ਹੋ ਸਕਿਆ। ਕਿਰਪਾ ਕਰਕੇ ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ।',
    emptySelection: 'ਕਿਰਪਾ ਕਰਕੇ ਸ਼ਾਮਲ ਕਰਨ ਲਈ ਘੱਟੋ-ਘੱਟ ਇੱਕ ਐਂਟਰੀ ਚੁਣੋ।',
  },
  'en-IN': {
    scanButton: 'Scan notebook',
    modalTitle: 'Scan old notebook',
    scanning: 'Scanning notebook...',
    safetyNote: 'Check names and amounts before adding.',
    thSelect: 'Select',
    thCustomer: 'Customer',
    thAmount: 'Amount (₹)',
    thType: 'Type',
    thNote: 'Note',
    newBadge: 'New',
    lowConfidence: 'Check',
    credit: 'Credit',
    payment: 'Payment',
    addAll: 'Add all selected',
    cancel: 'Cancel',
    successToast: (n) => `Added ${n} entries to ledger`,
    noRowsFound: 'No ledger entries found on this page. Please try a clearer photo.',
    errFileSize: 'File size exceeds 8 MB limit.',
    errFileType: 'Please select a valid image file (JPG, PNG, WEBP, or HEIC).',
    errGeneric: 'Could not process notebook image. Please try again.',
    emptySelection: 'Please select at least one entry to add.',
  },
};

export const getScanStrings = (langCode) => {
  return SCAN_TRANSLATIONS[langCode] || SCAN_TRANSLATIONS['hi-en'] || SCAN_TRANSLATIONS['en-IN'];
};

export function setupScanFeature({
  scanButton,
  scanFileInput,
  scanModal,
  scanBackdrop,
  scanCloseButton,
  scanCancelButton,
  scanConfirmButton,
  scanPreviewImage,
  scanSweepOverlay,
  scanStatusText,
  scanTableWrap,
  scanTableBody,
  scanSelectAll,
  scanButtonLabel,
  scanModalTitle,
  scanSafetyText,
  thPerson,
  thAmount,
  thType,
  thNote,
  getSelectedLanguage,
  showNotice,
  refreshLedger,
}) {
  let currentPreviewUrl = null;
  let currentDrafts = [];

  const isMobileDevice = () => {
    return (
      /Android|iPhone|iPad|iPod/i.test(navigator.userAgent) ||
      ('ontouchstart' in window && window.innerWidth <= 768)
    );
  };

  const updateLabels = () => {
    const lang = getSelectedLanguage();
    const t = getScanStrings(lang);
    if (scanButtonLabel) scanButtonLabel.textContent = t.scanButton;
    if (scanModalTitle) scanModalTitle.textContent = t.modalTitle;
    if (scanSafetyText) scanSafetyText.textContent = t.safetyNote;
    if (scanStatusText) scanStatusText.textContent = t.scanning;
    if (scanCancelButton) scanCancelButton.textContent = t.cancel;
    if (scanConfirmButton) scanConfirmButton.textContent = t.addAll;
    if (thPerson) thPerson.textContent = t.thCustomer;
    if (thAmount) thAmount.textContent = t.thAmount;
    if (thType) thType.textContent = t.thType;
    if (thNote) thNote.textContent = t.thNote;
  };

  const closeModal = () => {
    if (currentPreviewUrl) {
      URL.revokeObjectURL(currentPreviewUrl);
      currentPreviewUrl = null;
    }
    if (scanFileInput) scanFileInput.value = '';
    if (scanPreviewImage) scanPreviewImage.src = '';
    if (scanModal) {
      scanModal.hidden = true;
      scanModal.setAttribute('aria-hidden', 'true');
    }
    if (scanSweepOverlay) scanSweepOverlay.hidden = true;
    if (scanTableWrap) scanTableWrap.hidden = true;
    if (scanTableBody) scanTableBody.innerHTML = '';
    if (scanConfirmButton) scanConfirmButton.disabled = true;
    currentDrafts = [];
  };

  const openModal = (previewUrl) => {
    updateLabels();
    if (scanPreviewImage) scanPreviewImage.src = previewUrl;
    if (scanSweepOverlay) scanSweepOverlay.hidden = false;
    if (scanTableWrap) scanTableWrap.hidden = true;
    if (scanConfirmButton) scanConfirmButton.disabled = true;
    if (scanModal) {
      scanModal.hidden = false;
      scanModal.setAttribute('aria-hidden', 'false');
    }
  };

  const renderTable = (drafts) => {
    currentDrafts = drafts.map((row) => ({
      ...row,
      selected: true,
      amount: Number(row.amount || 0),
      note: row.note || '',
    }));

    const lang = getSelectedLanguage();
    const t = getScanStrings(lang);
    if (!scanTableBody) return;
    scanTableBody.innerHTML = '';

    currentDrafts.forEach((row, index) => {
      const tr = document.createElement('tr');
      tr.className = `scan-row ${row.confidence === 'low' ? 'low-confidence' : ''}`;
      tr.dataset.index = String(index);

      // Checkbox
      const tdCheck = document.createElement('td');
      tdCheck.className = 'col-check';
      const check = document.createElement('input');
      check.type = 'checkbox';
      check.className = 'scan-row-check';
      check.checked = true;
      check.setAttribute('aria-label', `Include ${row.person}`);
      check.addEventListener('change', () => {
        row.selected = check.checked;
        updateConfirmButtonState();
      });
      tdCheck.appendChild(check);

      // Customer name
      const tdPerson = document.createElement('td');
      tdPerson.className = 'col-person';
      const personWrap = document.createElement('div');
      personWrap.className = 'person-input-wrap';
      const personInput = document.createElement('input');
      personInput.type = 'text';
      personInput.className = 'scan-input-person';
      personInput.value = row.person;
      personInput.addEventListener('input', (e) => {
        row.person = e.target.value.trim();
        updateConfirmButtonState();
      });
      personWrap.appendChild(personInput);

      if (row.is_new_customer) {
        const badge = document.createElement('span');
        badge.className = 'badge badge-new';
        badge.textContent = t.newBadge;
        personWrap.appendChild(badge);
      }
      if (row.confidence === 'low') {
        const badge = document.createElement('span');
        badge.className = 'badge badge-low';
        badge.textContent = t.lowConfidence;
        badge.title = 'Low confidence detection';
        personWrap.appendChild(badge);
      }
      tdPerson.appendChild(personWrap);

      // Amount
      const tdAmount = document.createElement('td');
      tdAmount.className = 'col-amount';
      const amountInput = document.createElement('input');
      amountInput.type = 'number';
      amountInput.step = 'any';
      amountInput.min = '1';
      amountInput.className = 'scan-input-amount';
      amountInput.value = row.amount;
      amountInput.addEventListener('input', (e) => {
        row.amount = Number(e.target.value);
        updateConfirmButtonState();
      });
      tdAmount.appendChild(amountInput);

      // Type toggle button
      const tdType = document.createElement('td');
      tdType.className = 'col-type';
      const typeToggle = document.createElement('button');
      typeToggle.type = 'button';
      typeToggle.className = `type-toggle ${row.type === 'credit_given' ? 'type-credit' : 'type-payment'}`;
      typeToggle.textContent = row.type === 'credit_given' ? t.credit : t.payment;
      typeToggle.addEventListener('click', () => {
        row.type = row.type === 'credit_given' ? 'payment_received' : 'credit_given';
        typeToggle.className = `type-toggle ${row.type === 'credit_given' ? 'type-credit' : 'type-payment'}`;
        typeToggle.textContent = row.type === 'credit_given' ? t.credit : t.payment;
      });
      tdType.appendChild(typeToggle);

      // Note
      const tdNote = document.createElement('td');
      tdNote.className = 'col-note';
      const noteInput = document.createElement('input');
      noteInput.type = 'text';
      noteInput.className = 'scan-input-note';
      noteInput.value = row.note;
      noteInput.placeholder = t.thNote;
      noteInput.addEventListener('input', (e) => {
        row.note = e.target.value;
      });
      tdNote.appendChild(noteInput);

      tr.append(tdCheck, tdPerson, tdAmount, tdType, tdNote);
      scanTableBody.appendChild(tr);
    });

    if (scanTableWrap) scanTableWrap.hidden = false;
    updateConfirmButtonState();
  };

  const updateConfirmButtonState = () => {
    if (!scanConfirmButton) return;
    const selected = currentDrafts.filter((r) => r.selected);
    scanConfirmButton.disabled = selected.length === 0;
    if (scanSelectAll) {
      scanSelectAll.checked = selected.length === currentDrafts.length && currentDrafts.length > 0;
    }
  };

  if (scanSelectAll) {
    scanSelectAll.addEventListener('change', () => {
      const checked = scanSelectAll.checked;
      currentDrafts.forEach((r) => (r.selected = checked));
      if (scanTableBody) {
        scanTableBody.querySelectorAll('.scan-row-check').forEach((chk) => {
          chk.checked = checked;
        });
      }
      updateConfirmButtonState();
    });
  }

  if (scanButton && scanFileInput) {
    scanButton.addEventListener('click', () => {
      if (isMobileDevice()) {
        scanFileInput.setAttribute('capture', 'environment');
      } else {
        scanFileInput.removeAttribute('capture');
      }
      scanFileInput.value = '';
      scanFileInput.click();
    });

    scanFileInput.addEventListener('change', async () => {
      const file = scanFileInput.files?.[0];
      if (!file) return;

      const lang = getSelectedLanguage();
      const t = getScanStrings(lang);

      if (file.size > 8 * 1024 * 1024) {
        showNotice(t.errFileSize, 'error');
        scanFileInput.value = '';
        return;
      }

      currentPreviewUrl = URL.createObjectURL(file);
      openModal(currentPreviewUrl);

      try {
        const formData = new FormData();
        formData.append('image', file);

        const response = await fetch('/scan-notebook', {
          method: 'POST',
          body: formData,
        });

        const data = await response.json().catch(() => ({}));
        console.log('Scan notebook response:', data);

        if (!response.ok) {
          throw new Error(data.detail || t.errGeneric);
        }

        if (scanSweepOverlay) scanSweepOverlay.hidden = true;

        const rows = data.drafts || data.entries || [];
        if (rows.length === 0) {
          showNotice(t.noRowsFound, 'error');
          closeModal();
          return;
        }

        renderTable(rows);
      } catch (err) {
        if (scanSweepOverlay) scanSweepOverlay.hidden = true;
        showNotice(err.message || t.errGeneric, 'error');
        closeModal();
      }
    });
  }

  if (scanConfirmButton) {
    scanConfirmButton.addEventListener('click', async () => {
      const lang = getSelectedLanguage();
      const t = getScanStrings(lang);

      const selected = currentDrafts.filter((r) => r.selected);
      if (selected.length === 0) {
        showNotice(t.emptySelection, 'error');
        return;
      }

      for (const row of selected) {
        if (!row.person.trim() || !Number.isFinite(row.amount) || row.amount <= 0) {
          showNotice(t.safetyNote, 'error');
          const index = currentDrafts.indexOf(row);
          const rowElement = scanTableBody?.querySelector(`tr[data-index="${index}"]`);
          const field = !row.person.trim()
            ? rowElement?.querySelector('.scan-input-person')
            : rowElement?.querySelector('.scan-input-amount');
          field?.focus();
          return;
        }
      }

      scanConfirmButton.disabled = true;
      scanConfirmButton.textContent = '...';

      try {
        const payload = {
          confirmation_id: `scan-${Date.now()}-${Math.random().toString(36).substring(2, 8)}`,
          confirmed: true,
          entries: selected.map((r) => ({
            person: r.person.trim(),
            amount: Number(r.amount),
            type: r.type === 'payment_received' ? 'payment_received' : 'credit_given',
            note: (r.note || '').trim() || 'Notebook entry',
          })),
        };

        const response = await fetch('/confirm', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });

        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(result.detail || 'Could not save scanned entries.');
        }

        closeModal();
        await refreshLedger();
        showNotice(t.successToast(selected.length), 'success');
      } catch (err) {
        showNotice(err.message || 'Failed to save entries.', 'error');
      } finally {
        if (scanConfirmButton) {
          scanConfirmButton.disabled = false;
          scanConfirmButton.textContent = t.addAll;
        }
      }
    });
  }

  if (scanCancelButton) scanCancelButton.addEventListener('click', closeModal);
  if (scanCloseButton) scanCloseButton.addEventListener('click', closeModal);
  if (scanBackdrop) scanBackdrop.addEventListener('click', closeModal);

  // Initial label sync
  updateLabels();

  return {
    updateLabels,
    closeModal,
  };
}
