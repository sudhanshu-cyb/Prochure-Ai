import requests

from config import Config


class LocationProvider:
    def search_vendors(self, query, location, radius=None):
        raise NotImplementedError


class GoogleLocationProvider(LocationProvider):
    def search_vendors(self, query, location, radius=None):
        if not Config.GOOGLE_MAPS_API_KEY:
            raise RuntimeError('Google Maps vendor search is not configured.')
        params = {
            'query': f'{query} {location}',
            'key': Config.GOOGLE_MAPS_API_KEY,
        }
        if radius:
            params['radius'] = radius
        response = requests.get(
            'https://maps.googleapis.com/maps/api/place/textsearch/json',
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get('results', [])


def get_location_provider():
    if Config.LOCATION_PROVIDER == 'google':
        return GoogleLocationProvider()
    raise ValueError(f'Unsupported location provider: {Config.LOCATION_PROVIDER}')
