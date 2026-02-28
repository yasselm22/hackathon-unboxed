import pydicom, numpy as np, matplotlib.pyplot as plt

def show_dicom(path: str):
    """Affiche une coupe DICOM avec ses métadonnées principales."""
    ds  = pydicom.dcmread(path)
    img = ds.pixel_array.astype(np.float32)
    img = (img - img.min()) / (img.max() - img.min() + 1e-8)

    fig, ax = plt.subplots(1, 1, figsize=(6, 6), facecolor="#111")
    ax.imshow(img, cmap="gray", interpolation="bilinear")
    ax.set_title(
        f"Patient: {getattr(ds,'PatientID','?')}  |  "
        f"Modality: {getattr(ds,'Modality','?')}  |  "
        f"Slice: {getattr(ds,'InstanceNumber','?')}",
        color="white", fontsize=10, pad=10
    )
    ax.axis("off")
    plt.tight_layout()
    plt.show()

    print(f"  Dimensions   : {img.shape}")
    print(f"  Pixel spacing: {getattr(ds,'PixelSpacing','N/A')}")
    print(f"  Study date   : {getattr(ds,'StudyDate','N/A')}")
    return ds

# ── Utilisation ───────────────────────────────────────
if __name__=="__main__":
    ds = show_dicom("/mnt/c/Users/elmou/hackathon-unboxed/study_1fc1a205/0301B7D6 0301B7D6/31981427 TC TRAX TC ABDOMEN TC PELVIS/CT CEV torax/CT000001.dcm")
    print("  Fonction show_dicom() prête ✓")