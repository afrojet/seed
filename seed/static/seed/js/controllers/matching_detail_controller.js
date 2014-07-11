/**
 * :copyright: (c) 2014 Building Energy Inc
 * :license: see LICENSE for more details.
 */
angular.module('BE.seed.controller.matching_detail', [])
.controller('matching_detail_controller', [
  '$scope',
  'building_services',
  function($scope, building_services) {
    $scope.building = {};
    $scope.detail = {};
    $scope.extra_matches = [];

    /**
     * toggle_match: calls $parent.toggle_match to create or destroy a match.
     *
     * @param {obj} building: the building to match or unmatch with $scope.building 
     */
    $scope.detail.toggle_match = function(building) {
        var no_coparent;

        $scope.$parent.toggle_match(
            $scope.building,
            building,
            building.matched
        );
        if (building.matched) {
            $scope.building.matched = true;
            // if there is allready a coparent add the nth match to `extra_matches`
            if ($scope.building.coparent && $scope.building.coparent.id &&
                $scope.building.coparent.id !== building.id) {
                if ($scope.extra_matches.indexOf(building.id) === -1) {
                    $scope.extra_matches.push(building.id);
                }

            } else {
                $scope.building.coparent = building;
            }
        } else {
            // remove coparent if unselected
            if ($scope.building.coparent && $scope.building.coparent.id === building.id) {
                $scope.building.coparent = {};
            }
            // remove an extra m2m selection
            if ($scope.extra_matches.indexOf(building.id) > -1) {
                $scope.extra_matches.splice(
                    $scope.extra_matches.indexOf(building.id), 1
                );
            }
            no_coparent = $scope.building.coparent || {};
            no_coparent = no_coparent.id || null;
            no_coparent = (no_coparent.id === null) ? true : false;
            // check if there are no more selections and set as unmatched
            if ($scope.extra_matches.length === 0 && no_coparent) {
                $scope.building.matched = false;
            }
        }
    };

    /*
     * event from parent controller (matching_controller) to pass intial data
     * load. 
     */
    $scope.$on('matching_loaded', function(event, data) {
        $scope.matching_buildings = data.matching_buildings;
        $scope.building = data.building;
    });

    $scope.init = function() {
        // reload matches here
    };
}]);