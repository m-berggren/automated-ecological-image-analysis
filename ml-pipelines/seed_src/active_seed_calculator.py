import json
import os


def calculate_polygon_area(poly):
    """
    Calculates the area of a polygon using the Shoelace formula adapted from
    https://www.geeksforgeeks.org/dsa/area-of-a-polygon-with-given-n-ordered-vertices/.
    Assumes poly is a flat list of coordinates: [x1, y1, x2, y2, x3, y3, x4, y4]
    """
    if len(poly) < 8:
        if len(poly) == 4:
            return abs((poly[2] - poly[0]) * (poly[3] - poly[1]))
        return 0.0

    x = poly[0::2]
    y = poly[1::2]
    area = 0.0
    n = len(x)
    for i in range(n):
        j = (i + 1) % n
        area += x[i] * y[j]
        area -= x[j] * y[i]

    return abs(area) / 2.0


def count_active_and_aborted_seeds(reference_seed, detected_seeds, threshold=0.30):
    """
    Categorizes the seeds into 'active' and 'aborted' based on the seed size.
    A seed that is <=threshold the size of the reference seed is considered 'aborted'.
    """
    if not reference_seed:
        raise ValueError('A reference seed polygon must be provided.')

    reference_area = calculate_polygon_area(reference_seed)
    threshold_area = reference_area * threshold

    active_count = 0
    aborted_count = 0

    for seed in detected_seeds:
        poly = seed['poly'] if isinstance(seed, dict) and 'poly' in seed else seed

        seed_area = calculate_polygon_area(poly)

        if seed_area <= threshold_area:
            aborted_count += 1
        else:
            active_count += 1

    total_count = active_count + aborted_count

    return {
        'total_seeds': total_count,
        'active_seeds': active_count,
        'aborted_seeds': aborted_count,
    }


# Testing that this works on our predictions, will probably change later once we have done the integration steps
if __name__ == '__main__':
    prediction_files_dir = '../ml-pipelines/predictions'
    for file_name in os.listdir(prediction_files_dir):
        file_path = os.path.join(prediction_files_dir, file_name)
        try:
            with open(file_path, 'r') as f:
                preds_list = json.load(f)
        except FileNotFoundError:
            print('Could not find preds file.')
            exit()

        # For now, just using the first seed in the list as the reference seed
        if len(preds_list) > 0:
            reference_seed = preds_list[0]['poly']
        else:
            print('No predictions found in the file.')
            exit()

        results = count_active_and_aborted_seeds(reference_seed, preds_list)
        print(f'{file_name} results: {results}')
