import json
import math
import os


def analyze_seed_confidence(predictions, risk_threshold=0.20):
    """
    Analyzes the confidence of a seed count prediction and calculates the overall confidence score.
    Calculates a possible seed count range based on the overall confidence score.
    Flags high-risk predictions that are above the risk_threshold.
    """
    total_count = len(predictions)

    # If no seeds were found
    if total_count == 0:
        return {
            'total_count': 0,
            'overall_confidence': 0.0,
            'estimated_range': (0, 0),
            'high_risk_flag': False,
            'reason': 'No seeds detected.',
        }

    # Aggregate overall confidence
    total_confidence = sum(seed.get('conf', 0.0) for seed in predictions)
    overall_confidence = total_confidence / total_count

    # Calculate the estimated range
    uncertainty_factor = 1.0 - overall_confidence
    error_margin = total_count * uncertainty_factor
    lower_bound = max(0, math.floor(total_count - error_margin))
    upper_bound = math.ceil(total_count + error_margin)

    # Flag high risk predictions (range outside threshold based on the total count)
    range_size = upper_bound - lower_bound
    max_allowed_range = total_count * risk_threshold

    is_high_risk = range_size > max_allowed_range

    return {
        'total_count': total_count,
        'overall_confidence': round(overall_confidence, 4),
        'estimated_range': (lower_bound, upper_bound),
        'high_risk_flag': is_high_risk,
        'range_size': range_size,
        'max_allowed_range': max_allowed_range,
    }


# Testing that this works on our predictions, will probably change later once we have done the integration steps
if __name__ == '__main__':
    prediction_files_dir = '../ml-pipelines/predictions'
    for file_name in os.listdir(prediction_files_dir):
        file_path = os.path.join(prediction_files_dir, file_name)
        try:
            with open(file_path, 'r') as f:
                predictions = json.load(f)
        except FileNotFoundError:
            print('Could not find preds file.')
            exit()

        results = analyze_seed_confidence(
            predictions, risk_threshold=0.20
        )  # +- 10% threshold

        print(f'=== {file_name} ===')
        print(f'Seed count: {results["total_count"]}')
        print(f'Overall confidence: {results["overall_confidence"] * 100:.2f}%')
        print(
            f'Estimated Range: {results["estimated_range"][0]} to {results["estimated_range"][1]} seeds'
        )

        if results['high_risk_flag']:
            print(
                f'Miscalculation risk: range size ({results["range_size"]:.0f})'
                + f' exceeds the threshold ({results["max_allowed_range"]:.0f}).'
            )
        print('-' * 30)
