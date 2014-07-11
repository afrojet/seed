/**
 * :copyright: (c) 2014 Building Energy Inc
 * :license: see LICENSE for more details.
 */
angular.module('BE.seed.controller.organization_settings', [])
.controller('settings_controller', [
    '$scope',
    '$log',
    'all_columns',
    'organization_payload',
    'query_threshold_payload',
    'shared_fields_payload',
    'auth_payload',
    'organization_service',
    '$filter',
    function (
      $scope,
      $log,
      all_columns,
      organization_payload,
      query_threshold_payload,
      shared_fields_payload,
      auth_payload,
      organization_service,
      $filter
    ) {
    $scope.fields = all_columns.fields;
    $scope.org = organization_payload.organization;
    $scope.select_all = false;
    $scope.filter_params = {};
    $scope.org.query_threshold = query_threshold_payload.query_threshold;
    $scope.auth = auth_payload.auth;

    /**
     * updates all the fields checkboxs to match the ``select_all`` checkbox
     */
    $scope.select_all_clicked = function () {
        var fields = $filter('filter')($scope.fields, $scope.filter_params);
        $scope.fields = $scope.fields.map(function (f) {
            if (fields.indexOf(f) !== -1){
                f.checked = $scope.select_all;
            }
            return f;
        });
    };

    /**
     * saves the updates settings
     */
    $scope.save_settings = function () {
        var fields = $scope.fields.filter(function (f) {
            return f.checked;
        });
        $scope.org.fields = fields;
        organization_service.save_org_settings($scope.org).then(function (data){
            // resolve promise
            $scope.settings_updated = true;
        }, function (data, status) {
            // reject promise
            $scope.$emit('app_error', data);
        });
    };

    /**
     * preforms from initial data processing:
     * - sets the checked shared fields
     */
    var init = function () {
        var sort_columns = shared_fields_payload.shared_fields.map(function (f) {
            return f.sort_column;
        });
        $scope.fields = $scope.fields.map(function (f) {
            if (sort_columns.indexOf(f.sort_column) !== -1) {
                f.checked = true;
            }
            return f;
        });
    };
    init();

}]);
