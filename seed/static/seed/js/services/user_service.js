/**
 * :copyright: (c) 2014 Building Energy Inc
 * :license: BSD 3-Clause, see LICENSE for more details.
 */
// user services
angular.module('BE.seed.service.user', []).factory('user_service', [
  '$http',
  '$q',
  'generated_urls',
  function ($http, $q, generated_urls) {
    var user_factory = {};
    var urls = generated_urls;

    var organization;

    /**
     * returns the current organization, set initially by a controller
     * @return {obj} organization
     */
    user_factory.get_organization = function() {
        // yes this is a global, but otherwise we'll have to use a promise in
        // front of every request that needs this. window.BE.initial_org_id is
        // set in base.html via the seed.views.main home view
        return organization || {
            id: window.BE.initial_org_id,
            name: window.BE.initial_org_name,
            user_role: window.BE.initial_org_user_role

        };
    };

    /**
     * sets the current organization
     * @param {obj} org
     * @return {promise}
     */
    user_factory.set_organization = function(org) {
        organization = org;
        var defer = $q.defer();
        $http({
            method: 'PUT',
            'url': urls.accounts.set_default_organization,
            'data': {
                'organization': org
            }
        }).success(function(data) {
            if (data.status === 'error') {
                defer.reject(data);
            }
            defer.resolve(data);
        }).error(function(data, status) {
            defer.reject(data, status);
        });
        return defer.promise;
    };

    user_factory.get_users = function() {

        var defer = $q.defer();
        $http.get(urls.accounts.get_users).success(function(data) {
            defer.resolve(data);
        }).error(function(data, status) {
            defer.reject(data, status);
        });
        return defer.promise;
    };

    user_factory.add = function(user) {
        var defer = $q.defer();

        var new_user_details = {'first_name': user.first_name, 
                                'last_name': user.last_name, 
                                'email': user.email,
                                'org_name': user.org_name,
                                'role': user.role
                               };

        if (typeof user.organization !== "undefined") {
            new_user_details.organization_id = user.organization.org_id;
        }

        $http({
            method: 'POST',
            'url': urls.accounts.add_user,
            'data': new_user_details
        }).success(function(data) {
            if (data.status === 'error') {
                defer.reject(data);
            }
            defer.resolve(data);
        }).error(function(data, status) {
            defer.reject(data, status);
        });
        return defer.promise;
    };

    user_factory.get_default_columns = function() {
        var defer = $q.defer();
        $http({
            method: 'GET',
            'url': urls.seed.get_default_columns
        }).success(function(data) {
            if (data.status === 'error') {
                defer.reject(data);
            }
            defer.resolve(data);
        }).error(function(data, status) {
            defer.reject(data, status);
        });
        return defer.promise;
    };

    user_factory.get_shared_buildings = function() {
        var defer = $q.defer();
        $http({
            method: 'GET',
            'url': urls.accounts.get_shared_buildings
        }).success(function(data) {
            if (data.status === 'error') {
                defer.reject(data);
            }
            defer.resolve(data);
        }).error(function(data, status) {
            defer.reject(data, status);
        });
        return defer.promise;
    };

    user_factory.set_default_columns = function(columns, show_shared_buildings) {
        var defer = $q.defer();
        $http({
            method: 'POST',
            'url': urls.seed.set_default_columns,
            'data': {'columns': columns, 'show_shared_buildings': show_shared_buildings}
        }).success(function(data) {
            if (data.status === 'error') {
                defer.reject(data);
            }
            defer.resolve(data);
        }).error(function(data, status) {
            defer.reject(data, status);
        });
        return defer.promise;
    };

    return user_factory;
}]);
