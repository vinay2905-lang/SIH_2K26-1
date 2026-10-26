# PRAMAAN test pack

Synthetic documents for trying PRAMAAN as an institution. Every certificate, name and number here is made up.

## How to use it

1. Sign in as **`sit.dehradun`** (password `Pramaan@2026`) and open application **APP-2026-00301**. It is a draft that still misses four documents.
2. **Complete it with the files in `1-clean/`.** Use the **Upload** button next to each item:

   - `Structural_stability.pdf` → **Structural stability certificate**
   - `Affidavit_undertaking.pdf` → **Affidavit (undertaking)**
   - `Faculty_list.pdf` → **Faculty list**
   - `Computer_lab_2.jpg` → **Computer-lab photograph**

   The pre-check runs after each upload. With all four, the application comes out **Clear** (risk 0).
3. **Try a problem file from `2-problems/`.** Upload it into the slot named below, then read the issues the page lists.
   - **Undo it:** for a photo, remove it with the bin icon next to it. For any other document, upload the clean file from `1-clean/` or `1-clean/already-in-the-draft/` into the same slot, which replaces it.
4. **See the official side.** Submit the application, then sign in as **`a.kulkarni`** and open it from the queue. The scrutiny workspace shows every finding, with the evidence highlighted on the page.
   - Some findings, such as suspected tampering, are shown **only to officials**. They are marked 🔒 below.
   - After you submit, the application can't be edited. To start again, reload the demo data: restart the service on Render, run `python -m app.seed` locally, or run `sudo bash deploy/reset-demo.sh` on a server.

The results below were recorded on 26-10-2026 by uploading each file into a fresh copy of the demo data. Date checks use the day you test, so the dates in the messages will differ. A certificate close to expiry starts getting a warning 60 days before it ends.

## Summary

| File | Upload into | Result |
|---|---|---|
| `01_FIRE_NOC__expired.pdf` | Fire NOC | Critical: Fire NOC lapsed before the application date (+2 more) · risk 49 |
| `02_FIRE_NOC__date_hidden_under_white_box.pdf` | Fire NOC | 🔒 High: Fire NOC: Text covered by a white box and replaced (+2 more) · risk 22 |
| `03_FIRE_NOC__fake_certificate_number.pdf` | Fire NOC | High: Fire NOC does not match the issuer's record · risk 12 |
| `04_FIRE_NOC__actually_a_land_deed.pdf` | Fire NOC | Warning: 04_FIRE_NOC__actually_a_land_deed.pdf looks like a Land document (registered deed) (+1 more) · risk 5 |
| `05_BUILDING_COMPLETION__edited_after_signing.pdf` | Building completion certificate | High: Building completion certificate does not match the issuer's record (+3 more) · risk 41 |
| `06_BUILDING_COMPLETION__not_signed.pdf` | Building completion certificate | Info: Building completion certificate: needs manual confirmation · risk 0 |
| `07_AFFILIATION_LETTER__lower_intake.pdf` | University affiliation letter | High: Requested intake exceeds the affiliation letter (+1 more) · risk 24 |
| `08_TER_RECEIPT__unknown_transaction.pdf` | TER payment receipt | High: TER payment receipt does not match the issuer's record · risk 12 |
| `09_FACULTY_LIST__unknown_faculty.pdf` | Faculty list | High: Faculty IDs not found in AICTE faculty records · risk 12 |
| `10_AFFIDAVIT__scanned_copy.pdf` | Affidavit (undertaking) | Warning: Affidavit (undertaking) is hard to read · risk 5 |
| `11_LAB_PHOTO__taken_far_from_campus.jpg` | Computer-lab photograph | Warning: Photo location is away from the campus · risk 5 |
| `12_LAB_PHOTO__copied_from_another_college.jpg` | Computer-lab photograph | 🔒 High: Computer-lab photograph matches a document from another institution · risk 12 |
| `13_ANY_SLOT__not_really_a_pdf.pdf` | Fire NOC | Upload refused |
| `14_LAB_PHOTO__pdf_instead_of_photo.pdf` | Computer-lab photograph | Upload refused |

🔒 = shown to officials only, not to the institution.

Even with the clean set, these documents have no online source to check against, so PRAMAAN asks the officer to confirm them by hand:

- **Info** · Structural stability certificate: needs manual confirmation
- **Info** · Affidavit (undertaking): needs manual confirmation

## Details: what PRAMAAN says about each file

### `01_FIRE_NOC__expired.pdf`

**Upload into:** Fire NOC  
**What is wrong:** Validity ended on 31-03-2026.

**Result:** risk 49, needs action.

- **Critical · Fire NOC lapsed before the application date**: The Fire NOC is valid till 31-03-2026, but the application is dated 26-10-2026. *(rule FIRE-NOC-01)*
- **High · Fire NOC validity differs from the application form**: The form declares the Fire NOC valid till 31-03-2027; the certificate says 31-03-2026. *(rule FIRE-NOC-02)*
- **High · Fire NOC does not match the issuer's record**: Differs from State fire NOC registry: valid till: issuer has 2027-03-31, document shows 2026-03-31. *(rule VERIFY-01)*

### `02_FIRE_NOC__date_hidden_under_white_box.pdf`

**Upload into:** Fire NOC  
**What is wrong:** The real date (31-03-2026) is covered with a white box and 31-03-2027 is typed on top.

**Result:** risk 22, needs review.

- 🔒 **High · Fire NOC: Text covered by a white box and replaced**: The file still contains “31-03-2026” under a white box; the visible text there is “31-03-2027”. *(rule FORENSIC-TEXT_COVERED)*
- 🔒 **Warning · Fire NOC: Saved with a document-editing tool**: File metadata names an editing tool (iLovePDF). *(rule FORENSIC-EDITING_TOOL)*
- 🔒 **Warning · Fire NOC: File changed after it was issued**: Created 28-03-2025, saved again 09-04-2026 (377 days later). *(rule FORENSIC-EDITED_LATER)*

### `03_FIRE_NOC__fake_certificate_number.pdf`

**Upload into:** Fire NOC  
**What is wrong:** The certificate number does not exist at the fire department.

**Result:** risk 12, needs review.

- **High · Fire NOC does not match the issuer's record**: State fire NOC registry has no record for FNOC/2025/DEH/40417. *(rule VERIFY-01)*

### `04_FIRE_NOC__actually_a_land_deed.pdf`

**Upload into:** Fire NOC  
**What is wrong:** A land deed uploaded in the Fire NOC slot.

**Result:** risk 5, minor issues.

- **Warning · 04_FIRE_NOC__actually_a_land_deed.pdf looks like a Land document (registered deed)**: Uploaded as Fire NOC, but the content reads like a Land document (registered deed). *(rule QUALITY-01)*
- **Info · Fire NOC: needs manual confirmation**: Reference number could not be read; confirm manually. *(rule VERIFY-01)*

### `05_BUILDING_COMPLETION__edited_after_signing.pdf`

**Upload into:** Building completion certificate  
**What is wrong:** Digitally signed, then the built-up area on it was changed (3,500 m2 added).

**Result:** risk 41, needs review.

- **High · Building completion certificate does not match the issuer's record**: File was changed after it was signed *(rule VERIFY-01)*
- 🔒 **High · Building completion certificate: Text covered by a white box and replaced**: The file still contains “22,600 m2” under a white box; the visible text there is “26,100 m2”. *(rule FORENSIC-TEXT_COVERED)*
- 🔒 **High · Building completion certificate: Signed document was changed after signing**: File was changed after it was signed *(rule FORENSIC-SIGNATURE_BROKEN)*
- **Warning · Built-up area differs from the completion certificate**: Form declares 22600 m²; the completion certificate shows 26100 m². *(rule BCC-01)*
- Digital signature: File was changed after it was signed.

### `06_BUILDING_COMPLETION__not_signed.pdf`

**Upload into:** Building completion certificate  
**What is wrong:** No digital signature.

**Result:** risk 0, clear.

- **Info · Building completion certificate: needs manual confirmation**: Not digitally signed and no online source; confirm with the issuing office. *(rule VERIFY-01)*

### `07_AFFILIATION_LETTER__lower_intake.pdf`

**Upload into:** University affiliation letter  
**What is wrong:** The university allows 90 seats in B.Tech CSE, but the application asks for 120.

**Result:** risk 24, needs review.

- **High · Requested intake exceeds the affiliation letter**: B.Tech Computer Science and Engineering: 120 requested, 90 in affiliation letter *(rule INTAKE-03)*
- **High · University affiliation letter does not match the issuer's record**: Differs from Affiliating-university API: intake B.Tech Computer Science and Engineering: issuer has 120, document shows 90. *(rule VERIFY-01)*

### `08_TER_RECEIPT__unknown_transaction.pdf`

**Upload into:** TER payment receipt  
**What is wrong:** The transaction ID is not in the payment gateway's records.

**Result:** risk 12, needs review.

- **High · TER payment receipt does not match the issuer's record**: Payment gateway has no record for TER-2026-00417. *(rule VERIFY-01)*

### `09_FACULTY_LIST__unknown_faculty.pdf`

**Upload into:** Faculty list  
**What is wrong:** Three faculty IDs are not in AICTE's faculty registry.

**Result:** risk 12, needs review.

- **High · Faculty IDs not found in AICTE faculty records**: Not found in AICTE records: FID-980000; FID-980001; FID-980002 *(rule FAC-01)*

### `10_AFFIDAVIT__scanned_copy.pdf`

**Upload into:** Affidavit (undertaking)  
**What is wrong:** A skewed, blurry scan with no text layer, so it has to be read by OCR.

**Result:** risk 5, minor issues.

- **Warning · Affidavit (undertaking) is hard to read**: Text could be read with only 0.55 confidence from 10_AFFIDAVIT__scanned_copy.pdf. Upload a clearer scan (300 dpi). *(rule QUALITY-01)*
- The file had no text layer, so it was read by OCR (confidence 0.55).

### `11_LAB_PHOTO__taken_far_from_campus.jpg`

**Upload into:** Computer-lab photograph  
**What is wrong:** The photo's GPS location is about 37 km from the campus.

**Result:** risk 5, minor issues.

- **Warning · Photo location is away from the campus**: Location tags far from the campus: 11_LAB_PHOTO__taken_far_from_campus.jpg (36.9 km away). Ask for fresh photos or a physical check. *(rule PHOTO-01)*

### `12_LAB_PHOTO__copied_from_another_college.jpg`

**Upload into:** Computer-lab photograph  
**What is wrong:** A re-saved copy of Wainganga Polytechnic's lab photo.

**Result:** risk 12, needs review.

- 🔒 **High · Computer-lab photograph matches a document from another institution**: 12_LAB_PHOTO__copied_from_another_college.jpg matches a near-identical photo (difference 0 of 64) filed by Wainganga Polytechnic in APP-2026-00087. *(rule FORENSIC-DUPLICATE)*

### `13_ANY_SLOT__not_really_a_pdf.pdf`

**Upload into:** Fire NOC  
**What is wrong:** A text file renamed to .pdf.

The upload is refused with the message *“Only PDF, JPEG and PNG files are accepted”*.

### `14_LAB_PHOTO__pdf_instead_of_photo.pdf`

**Upload into:** Computer-lab photograph  
**What is wrong:** A PDF uploaded in the photo slot.

The upload is refused with the message *“Upload photographs as JPEG or PNG”*.
