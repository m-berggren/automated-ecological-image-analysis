import pandas as pd


def extract_morphology(sahi_result, ppm=1.0):
    """
    Extracts dimensions from SAHI OBB predictions.
    ppm: Pixels Per Millimeter (calibration factor)
    """
    seeds_data = []

    for pred in sahi_result.object_prediction_list:
        # For OBB, the width and height represent the axes of the rotated box
        w_px = pred.bbox.w
        h_px = pred.bbox.h

        # Ensure 'length' is always the larger dimension
        length_px = max(w_px, h_px)
        width_px = min(w_px, h_px)

        # Convert to mm
        length_mm = length_px / ppm
        width_mm = width_px / ppm
        area_mm2 = length_mm * width_mm  # Approximation for rectangular OBB

        seeds_data.append(
            {
                'length_mm': length_mm,
                'width_mm': width_mm,
                'area_mm2': area_mm2,
                'aspect_ratio': length_mm / width_mm,
            }
        )

    return pd.DataFrame(seeds_data)


def calculate_seed_viability(df):
    """
    Categorizes seeds based on the 30% size rule.
    """
    # Use Median to establish a more stable 'typical' seed size
    baseline_area = df['area_mm2'].median()
    threshold = baseline_area * 0.30

    # Categorize
    df['status'] = np.where(df['area_mm2'] <= threshold, 'Aborted', 'Active')

    # Summary Stats
    counts = df['status'].value_counts().to_dict()
    active_count = counts.get('Active', 0)
    aborted_count = counts.get('Aborted', 0)

    return active_count, aborted_count, threshold


def plot_viability_report(df, threshold, active_count, aborted_count):
    plt.figure(figsize=(10, 6))

    # Plot Active vs Aborted with different colors
    active_seeds = df[df['status'] == 'Active']['area_mm2']
    aborted_seeds = df[df['status'] == 'Aborted']['area_mm2']

    plt.hist(
        active_seeds,
        bins=25,
        color='#2ecc71',
        alpha=0.7,
        label=f'Active ({active_count})',
    )
    plt.hist(
        aborted_seeds,
        bins=5,
        color='#e74c3c',
        alpha=0.7,
        label=f'Aborted ({aborted_count})',
    )

    # Add the "Cut-off" line
    plt.axvline(threshold, color='black', linestyle='--', linewidth=2)
    plt.text(
        threshold, plt.ylim()[1] * 0.9, ' 30% Threshold', rotation=0, fontweight='bold'
    )

    plt.title('Seed Viability & Morphological Profile')
    plt.xlabel('Seed Area (mm²)')
    plt.ylabel('Frequency')
    plt.legend()

    # Add a 'Health Index' box
    health_ratio = (active_count / (active_count + aborted_count)) * 100
    plt.figtext(
        0.15,
        0.8,
        f'Batch Health: {health_ratio:.1f}%',
        bbox=dict(facecolor='white', edgecolor='black', boxstyle='round,pad=1'),
    )

    plt.savefig('viability_report.png')
