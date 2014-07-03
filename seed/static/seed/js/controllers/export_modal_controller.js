/**
 * :copyright: (c) 2014 Building Energy Inc
 * :license: BSD 3-Clause, see LICENSE for more details.
 */
angular.module('BE.seed.controller.export_modal', [])
.controller('export_modal_controller', [
  '$scope',
  '$modalInstance',
  'search',
  'selected_fields',
  'project',
  'export_service',
  '$timeout',
  function($scope, $modalInstance, search, selected_fields, project, export_service, $timeout) {
    $scope.export_state = 'create';
    $scope.building_export = {};
    $scope.building_export.selected_fields = selected_fields;
    $scope.building_export.selected_buildings = search.selected_buildings;
    $scope.building_export.filter_params = search.filter_params;
    $scope.building_export.select_all_checkbox = search.select_all_checkbox;
    $scope.building_export.order_by = search.order_by;
    $scope.building_export.sort_reverse = search.sort_reverse;
    $scope.building_export.export_type = "xls";
    $scope.building_export.export_name = "";
    $scope.building_export.project_id = project.id || null;
    $scope.progress_percentage = 1;
    $scope.progress_numerator = 0;
    $scope.progress_denominator = 0;

    /**
     * export_buildings: starts the export process by sending the 
     *   $scope.building_export object to the `export_buildings` service call.
     *   On `export_buildings` success, `$scope.monitor_progress is called
     *   and the progress bar is shown.
     *
     *   The Export Name and file type (CSV or XLS) is part of the $scope.
     *   building_export payload.
     *
     *   Send project_id as the id or null
     */
    $scope.export_buildings = function () {
        $scope.progress_percentage = 0;
        $scope.export_state = 'prepare';
        export_service.export_buildings($scope.building_export).then(
          function (data) {
            // resolve promise
            $scope.monitor_progress(data.export_id, data.total_buildings);
        });
    };

    /**
     * monitor_progress: call loop to update the progress bar.
     *
     * @param {string} export_id: the export file id generated by the server 
     */
    $scope.monitor_progress = function (export_id, total_buildings) {
        $scope.stop = $timeout(function () {
            export_service.export_buildings_progress(export_id).then(
              function (data) {
                // resolve promise
                // update progress bar
                $scope.progress_percentage = (data.buildings_processed / total_buildings) * 100;
                $scope.progress_numerator = data.buildings_processed;
                $scope.progress_denominator = total_buildings;
                // continue loop or move to export page
                if (data.buildings_processed < total_buildings) {
                    $scope.monitor_progress(export_id, total_buildings);
                } else {
                    $scope.show_success_page(export_id);
                }
            }, function (data, status) {
                // reject promise
                console.log({data: data, status: status});
            });
        }, 250);

    };

    /**
     * show_success_page: shows the success page once the download is ready
     *
     * @param {string} export_id: the export file id generated by the server
     */
    $scope.show_success_page = function (export_id) {
        export_service.export_buildings_download(export_id).then(
          function (data) {
            // resolve promise
            $scope.export_state = 'success';
            window.location = data.url;
          }, function (data, status) {
            // reject promise
            console.log({data: data, status: status});
          }
        );
    };

    /**
     * cancel: dismisses the modal
     */
    $scope.cancel = function () {
        // stop any remaining timeout loops
        $timeout.cancel($scope.stop);
        $modalInstance.dismiss('cancel');
    };

    /**
     * close: closes the modal
     */
    $scope.close = function () {
        // stop any remaining timeout loops
        $timeout.cancel($scope.stop);
        $modalInstance.close();
    };
}]);
