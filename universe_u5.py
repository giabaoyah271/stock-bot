"""KT17.0: user-approved candidate watchlist, NOT cleared trading universe."""
U5_VERSION="U5-2026-11-25-v1"
REVIEW_SINCE="2025-01-01"
OLD_KEPT=(
    "SSI", "VIX", "VND", "SHS", "HPG", "DIG", "PDR", "STB", "MBB", "TCB",
    "VPB", "SHB", "ACB", "DXG", "VCI", "HCM", "CEO", "HAG", "HSG", "NKG",
    "GVR", "FPT", "MWG", "MSN", "VIC", "VHM", "VCB", "BID", "CTG", "LPB",
    "HDB", "TPB", "MSB", "OCB", "EIB", "VIB", "DPM", "DCM", "PVD", "PVS",
    "PVT", "BSR", "GAS", "PLX", "POW", "VRE", "GMD", "HAH", "VJC", "VPX",
    "REE", "MCH", "VCG", "HHV", "LCG", "VCK", "FCN", "CII", "KBC", "SZC",
    "IDC", "GEX", "VNM", "FRT", "FTS", "NLG", "DGW", "BAF", "CTD", "SAB",
    "PNJ", "DBC", "PAN", "ANV", "VGC", "VHC", "GEG", "NT2", "HDC", "TV2",
    "CSV", "BFC", "LAS", "PHR", "DPR", "TCH", "MSH", "TCM", "CTS", "GEE",
    "KDH", "BSI", "HUT", "TNG", "VGS", "MBS", "AGR", "BVH", "SSB", "PC1",
)
NEW_ADDED=(
    "ACV", "VPL", "DMX", "TCX", "MSR", "VEA", "FOX", "BCM", "NAB", "ABB",
    "PGV", "GEL", "SBT", "QNS", "VBB", "CC1", "PVI", "PHP", "KDC", "TAL",
)
EXCLUDED=(
    "DGC", "VPI", "NVL", "HVN", "NVB", "VGI", "SJS", "VNZ", "MVN", "VSF",
    "KSF", "KSV", "SSH", "DNH", "LGC", "VEF", "IDP", "THD", "LPS", "CRV",
    "HGI",
)
U5=tuple(sorted(OLD_KEPT+NEW_ADDED))
assert len(U5)==120 and len(set(U5))==120
assert len(set(U5+EXCLUDED))==141
BATCHES={f"B{i+1}":U5[i*30:(i+1)*30] for i in range(4)}

# A verified disclosure notice, not a determination of materiality/clearance.
# Unreviewed symbols must not be represented as cleared.
KNOWN_NOTICES={
    "PC1":("2026-11-23","UBCKNN: phạt 92,5 triệu đồng do chậm CBTT; cần đánh giá tính trọng yếu và khắc phục.",
           "https://ssc.gov.vn/webcenter/portal/ubck/pages_r/l/chitit?dDocName=APPSSCGOVVN1620176375")
}
