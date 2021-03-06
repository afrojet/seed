/**
 * :copyright: (c) 2014 Building Energy Inc
 * :license: see LICENSE for more details.
 */
angular.module('BE.seed.controller.matching', [])
.controller('matching_controller', [
    '$scope',
    'import_file_payload',
    'buildings_payload',
    'building_services',
    'default_columns',
    'all_columns',
    'urls',
    '$modal',
    '$log',
    'search_service',
    function($scope, import_file_payload, buildings_payload, building_services, default_columns, all_columns, urls, $modal, $log, search_service) {
    $scope.search = angular.copy(search_service);
    $scope.search.url = urls.search_buildings;

    $scope.import_file = import_file_payload.import_file;
    $scope.buildings = buildings_payload.buildings;
    console.log({import_file: import_file_payload, bld_payload: buildings_payload});
    $scope.q = "";
    $scope.number_per_page = 10;
    $scope.current_page = 1;
    $scope.order_by = "";
    $scope.sort_reverse = false;
    $scope.filter_params = {};
    $scope.existing_filter_params = {};
    $scope.project_slug = null;
    $scope.number_matching_search = 0;
    $scope.number_returned = 0;
    $scope.pagination = {};
    $scope.prev_page_disabled = false;
    $scope.next_page_disabled = false;
    $scope.showing = {};
    $scope.pagination.number_per_page_options = [10, 25, 50, 100];
    $scope.pagination.number_per_page_options_model = 10;
    $scope.pills = {};
    $scope.loading_pills = true;
    $scope.show_building_list = true;
    $scope.selected_row = "";
    $scope.fields = all_columns.fields;
    $scope.default_columns = default_columns.columns;
    $scope.columns = [];
    var conf_range = {};
    $scope.alerts = [];
    $scope.file_select = {};
    $scope.file_select.file = $scope.import_file.dataset.importfiles[0];
    

    /*
     * filter_search: searches TODO(ALECK): use the search_service for search
     *   and pagination here.
     */
    $scope.filter_search = function() {
        $scope.update_number_matched();
        building_services.search_matching_buildings($scope.q, $scope.number_per_page, $scope.current_page,
            $scope.order_by, $scope.sort_reverse, $scope.filter_params, $scope.file_select.file.id).then(
            function(data) {
                // resolve promise
                // safe-guard against furutre init() calls
                buildings_payload = data;

                $scope.buildings = data.buildings;
                $scope.number_matching_search = data.number_matching_search;
                $scope.number_returned = data.number_returned;
                $scope.num_pages = Math.ceil(data.number_matching_search / $scope.number_per_page);
                update_start_end_paging();
            },
            function(data, status) {
                // reject promise
                console.log({data: data, status: status});
                $scope.alerts.push({ type: 'danger', msg: 'Error searching' });
            }
        );
    };

     $scope.closeAlert = function(index) {
        $scope.alerts.splice(index, 1);
    };

    $scope.filter_by_matched = function() {
        // only show matched buildings
        $scope.filter_params.children__isnull = false;
        $scope.current_page = 1;
        $scope.filter_search();
    };

    $scope.filter_by_unmatched = function() {
        // only show unmatched buildings
        $scope.current_page = 1;
        $scope.filter_params.children__isnull = true;
        $scope.filter_search();
    };

     /**
     * Pagination code
     */
    $scope.pagination.update_number_per_page = function() {
        $scope.number_per_page = $scope.pagination.number_per_page_options_model;
        $scope.filter_search();
    };
    var update_start_end_paging = function() {
        if ($scope.current_page === $scope.num_pages) {
            $scope.showing.end = $scope.number_matching_search;
        } else {
            $scope.showing.end = ($scope.current_page) * $scope.number_per_page;
        }

        $scope.showing.start = ($scope.current_page - 1) * $scope.number_per_page + 1;
        $scope.prev_page_disabled = $scope.current_page === 1;
        $scope.next_page_disabled = $scope.current_page === $scope.num_pages;

    };
    $scope.pagination.next_page = function() {
        $scope.current_page += 1;
        if ($scope.current_page > $scope.num_pages) {
            $scope.current_page = $scope.num_pages;
        }
        $scope.filter_search();
    };
    $scope.pagination.prev_page = function() {
        $scope.current_page -= 1;
        if ($scope.current_page < 1) {
            $scope.current_page = 1;
        }
        $scope.filter_search();
    };
    /**
     * end pagination code
     */

    /**
     * toggle_match: creates or removes a match between a building and
     *   co_porent or suggested co_parent. Triggered by `ng-change` on
     *   `building.matched` therefore `building.matched` refers to the future
     *   state of match/unmatch.
    
            // building with id 1 matched with coparent with id 2 and their
            // child with id 11
            building_with_match = {
                id: 1,
                children: [11],
                coparent: {
                    id: 2,
                    children: [11]
                }
            }
            // building without a coparent and child
            building_without_match = {
                id: 1,
                children: []
            }
     *
     * @param {obj} building: building object to match or unmatch
     * @param {obj} target_building: building to match against. Called
     *   explicitly from child scope via $scope.$parent.toggle_match.
     * @param {bool} create: overrite to create or not create a match
     */
    $scope.toggle_match = function(building, target_building, create) {
        var source_building_id,
            target_building_id,
            create_match,
            coparent = building.coparent || {};
        $scope.$emit('show_saving');
        coparent.id = coparent.id || null;
        if (typeof create !== 'undefined' && create !== null) {
            create_match = create;
        } else {
            create_match = building.matched;
        }
        source_building_id = (create_match) ? building.id : building.children[0];
        target_building = target_building || {};
        target_building_id = target_building.id || coparent.id;

        // creates or removes a match
        building_services.save_match(
            source_building_id,
            target_building_id,
            create_match
        ).then(function(data) {
            // resolve promise
            // update building and coparent's child in case of a unmatch 
            // without a page refresh
            if (building.matched) {
                building.children = building.children || [0];
                building.children[0] = data.child_id;
            }
            $scope.update_number_matched();
            $scope.$emit('finished_saving');
        }, function(data, status) {
            // reject promise
            building.matched = !building.matched;
            console.log({data: data, status:status});
            $scope.$emit('finished_saving');
        });
    };
    
    /*
     * match_building: loads/shows the matching detail table and hides the 
     *  matching list table
     */
    $scope.match_building = function(building) {
        // shows a matched building detail page
        $scope.search.filter_params = {};
        if (building.children.length > 0) {
            $scope.search.filter_params.exclude = {
                id: building.children[0]
            };
        } else {
            $scope.search.filter_params.exclude = {
                id: building.id
            };
        }
        $scope.search.search_buildings().then(function(data){
            
            $scope.$broadcast('matching_loaded', {
                matching_buildings: data.buildings,
                building: building
            });
            console.log({building: building});
            $scope.show_building_list = false;
            $scope.selected_row = building.id;
        });

    };

    /**
     * open_edit_columns_modal: opens the edit columns modal to select and set
     *   the columns used in the matching list table and matching detail table
     */
    $scope.open_edit_columns_modal = function() {
        var modalInstance = $modal.open({
            templateUrl: urls.static_url + 'seed/partials/custom_view_modal.html',
            controller: 'custom_view_modal_ctrl',
            resolve: {
                'all_columns': function() {
                    return {
                        fields: $scope.fields
                    };
                },
                'selected_columns': function() {
                    return $scope.columns.map(function(c){
                        return c.sort_column;
                    });
                },
                'buildings_payload': function() {
                    return {};
                }
            }
        });

        modalInstance.result.then(
            function (columns) {
                // reload columns
                $scope.default_columns = columns;
                $scope.columns = building_services.create_column_array($scope.fields, columns);
        }, function (message) {
        });
    };


    /**
     * update_number_matched: updates the number of matched and unmatched
     *   buildings
     */
    $scope.update_number_matched = function() {
        building_services.get_PM_filter_by_counts($scope.file_select.file.id)
        .then(function (data){
            // resolve promise
            $scope.matched_buildings = data.matched;
            $scope.unmatched_buildings = data.unmatched;
        });
    };

    /**
     * back_to_list: shows the matching list table, hides the matching detail
     *   table
     */
    $scope.back_to_list = function() {
        $scope.show_building_list = true;
    };

    /**
     * init: sets the default pagination, gets the columns that should be displayed
     *   in the matching list table, sets the table buildings from the building_payload
     */
    $scope.init = function() {
        $scope.columns = building_services.create_column_array($scope.fields, $scope.default_columns);
        update_start_end_paging();
        $scope.buildings = buildings_payload.buildings;
        $scope.number_matching_search = buildings_payload.number_matching_search;
        $scope.number_returned = buildings_payload.number_returned;
        $scope.num_pages = Math.ceil(buildings_payload.number_matching_search / $scope.number_per_page);
        
        $scope.update_number_matched();
    };
    $scope.init();
}]);
