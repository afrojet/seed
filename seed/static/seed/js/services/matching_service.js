/**
 * :copyright: (c) 2014 Building Energy Inc
 * :license: BSD 3-Clause, see LICENSE for more details.
 */

// matching services
angular.module('BE.seed.service.matching', []).factory('matching_service', [
  '$http',
  '$q',
  '$timeout',
  'user_service',
  function ($http, $q, $timeout, user_service) {

    var matching_factory = {};

    /*
     *Start system matching
     *
     *@param import_file_id: int, the database id of the import file
     * we wish to match against other buildings for an organization.
     */
    matching_factory.start_system_matching = function(import_file_id) {
        var defer = $q.defer();
        $http({
            method: 'POST',
            'url': window.BE.urls.start_system_matching,
            'data': {
                'file_id': import_file_id,
                'organization_id': user_service.get_organization().id
            }
        }).success(function(data, status, headers, config) {
            defer.resolve(data);
        }).error(function(data, status, headers, config) {
            defer.reject(data, status);

        });
        return defer.promise;
    };

   return matching_factory;
}]);
