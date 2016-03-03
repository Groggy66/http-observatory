from httpobs.scanner.grader import get_test_score_description
from httpobs.scanner.tasks import scan
from httpobs.scanner.utils import valid_hostname
from httpobs.website import add_response_headers, sanitized_api_response

from flask import Blueprint, abort, request
from os import environ

import httpobs.database as database

api = Blueprint('api', __name__)


COOLDOWN = 15 if 'HTTPOBS_DEV' in environ else 300


# TODO: Implement API to write public and private headers to the database

@api.route('/api/v1/analyze', methods=['GET', 'POST'])
@add_response_headers()
@sanitized_api_response
def api_post_scan_hostname():
    # Get the hostname
    hostname = request.args.get('host', '').lower()

    # Fail if it's not a valid hostname (not in DNS, not a real hostname, etc.)
    hostname = valid_hostname(hostname) or valid_hostname('www.' + hostname)  # prepend www. if necessary
    if not hostname:
        return {'error': '{hostname} is an invalid hostname'.format(hostname=request.args.get('host', ''))}

    # Get the site's id number
    try:
        site_id = database.select_site_id(hostname)
    except IOError:
        return {'error': 'Unable to connect to database'}

    # Next, let's see if there's a recent scan; if there was a recent scan, let's just return it
    # Setting rescan shortens what "recent" means
    rescan = True if 'rescan' in request.form else False
    if rescan:
        row = database.select_scan_recent_scan(site_id, COOLDOWN)
    else:
        row = database.select_scan_recent_scan(site_id)

    # Otherwise, let's start up a scan
    if not row:
        row = database.insert_scan(site_id)
        scan_id = row['id']

        # Begin the dispatch process if it was a POST
        if request.method == 'POST':
            scan.delay(hostname, site_id, scan_id)
        else:
            return {'error': 'recent-scan-not-found'}

    # If there was a rescan attempt and it returned a row, it's because the rescan was done within the cooldown window
    elif rescan and request.method == 'POST':
        return {'error': 'rescan-attempt-too-soon'}

    # Return the scan row
    return row


@api.route('/api/v1/getScanResults', methods=['GET'])
@add_response_headers()
@sanitized_api_response
def api_get_test_results():
    scan_id = request.args.get('scan')

    if not scan_id:
        return {'error': 'scan-not-found'}

    # Get all the test results for the given scan id
    tests = dict(database.select_test_results(scan_id))

    # For each test, get the test score description and add that in
    for test in tests:
        tests[test]['score_description'] = get_test_score_description(tests[test]['result'])

    return tests