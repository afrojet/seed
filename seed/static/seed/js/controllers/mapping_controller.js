/**
 * :copyright: (c) 2014 Building Energy Inc
 * :license: see LICENSE for more details.
 */
angular.module('BE.seed.controller.mapping', [])
.controller('mapping_controller', [
  '$scope',
  'import_file_payload',
  'suggested_mappings_payload',
  'raw_columns_payload',
  'first_five_rows_payload',
  'all_columns',
  'building_services',
  '$timeout',
  'mappingValidatorService',
  'mapping_service',
  'search_service',
  'urls',
  '$modal',
  'user_service',
  'matching_service',
  'uploader_service',
  function (
    $scope,
    import_file_payload,
    suggested_mappings_payload,
    raw_columns_payload,
    first_five_rows_payload,
    all_columns,
    building_services,
    $timeout,
    mappingValidatorService,
    mapping_service,
    search_service,
    urls,
    $modal,
    user_service,
    matching_service,
    uploader_service
) {
    $scope.tabs = {
      'one_active': true,
      'two_active': false,
      'three_active': false
    };
    $scope.import_file = import_file_payload.import_file;
    $scope.import_file.matching_finished = false;
    $scope.suggested_mappings = suggested_mappings_payload.suggested_column_mappings;
    $scope.raw_columns = raw_columns_payload.raw_columns;
    $scope.first_five = first_five_rows_payload.first_five_rows;
    $scope.building_column_types = suggested_mappings_payload.building_column_types;
    $scope.validator_service = mappingValidatorService;
    $scope.user = $scope.user || {};
    // Where we store which columns get concatenated and in which order.
    // Keyed on destination mapping name.

    $scope.review_mappings = false;
    $scope.show_mapped_buildings = false;

    $scope.search = angular.copy(search_service);
    $scope.search.url = urls.search_PM_buildings;
    $scope.search.has_checkbox = false;
    $scope.search.update_results();

    /*
     * Opens modal for making changes to concatenation changes.
     */
    $scope.open_concat_modal = function(building_column_types, raw_columns) {
        var concatModalInstance = $modal.open({
            templateUrl: urls.static_url + 'seed/partials/concat_modal.html',
            controller: 'concat_modal_ctrl',
            resolve: {
                building_column_types: function() {
                    return Object.keys(building_column_types);
                },
                raw_columns: function() {
                    return raw_columns;
               }
            }
         });
    };

    /*
     * Gets the row-level validity for a Table Column Mapping.
     *
     * @param tcm: table column mapping object.
     * @param to_validate: array of strings, values from example data.
     */
    $scope.get_validity = function(tcm) {
        var diff = tcm.raw_data.length - tcm.invalids.length;
        // Used to display the state of the row overall.
        if (typeof(tcm.invalids) === "undefined") {
            return undefined;
        }
        if ( tcm.invalids.length === 0) {
            return 'valid';
        }
        if (diff > 1) {
            return 'semivalid';
        }
        if (diff < 1) {
            return 'invalid';
        }

     };

    /*
     * set_td_class
     * Gets called on each cell in a table on the mapping page.
     * Return true if a column value is invalid for a TCM.
     */
    $scope.set_td_class = function(tcm, col_value) {
        // If we don't want to map a column, don't validate it.
        tcm = tcm || {};
        if (tcm.suggestion === '') {
            return '';
        }
        if (tcm.validity === 'valid')  {
            return 'success';
        }
        for (
            var i = 0; typeof tcm.invalids !== "undefined" &&
            i < tcm.invalids.length; i++
        ) {
            if (col_value === tcm.invalids[i]) {
                if (tcm.validity === 'semivalid') {
                    return 'warning';
                }
                return 'danger';
            }
        }
    };

    $scope.find_duplicates = function (array, element) {
        var indicies = [];
        var idx = array.indexOf(element);
        while (idx !== -1) {
            indicies.push(idx);
            idx = array.indexOf(element, idx + 1);
        }
        return indicies;
    };

    /*
     * Returns true if a TCM row is duplicated elsewhere.
     */
    $scope.is_tcm_duplicate = function(tcm) {
        var suggestions = [];
        for (var i = 0; i < $scope.raw_columns.length; i++){
            var potential = $scope.raw_columns[i].suggestion;
            if (typeof potential === 'undefined' ||
                    potential === ''
            ) {
                continue;
            }
            suggestions.push($scope.raw_columns[i].suggestion);
        }
        var dups = $scope.find_duplicates(suggestions, tcm.suggestion);
        if (dups.length > 1) {
            return true;
        }
        return false;
    };

    /*
     * Validates example data related to a raw column using a validator service.
     *
     * @param tcm: a table column mapping object.
     * @modifies: attributes on that mapping object.
     */
    $scope.validate_data = function(tcm) {
        tcm.user_suggestion = true;
        if (typeof(tcm.suggestion) !== "undefined" && tcm.suggestion !== '') {
            var type = $scope.building_column_types[tcm.suggestion];
            tcm.suggestion_type = type;
            tcm.invalids = $scope.validator_service.validate(
                tcm.raw_data, type
            );
            tcm.validity = $scope.get_validity(tcm);
        } else {
            tcm.validity = null;
            tcm.invalids = [];
        }
    };

    /*
     * change: called when a user selects a mapping change. `change` should
     * either save the new mapping to the back-end or wait until all mappings
     * are complete.
     *
     * `change` should indicate to the user if a table column is already mapped
     * to another csv raw column header
     *
     * @param tcm: table column mapping object. Represents the BS <-> raw
     *  relationship.
     */
    $scope.change = function(tcm) {
        // Validate that the example data will convert.
        $scope.validate_data(tcm);
        // Verify that we don't have any duplicate mappings.
        for (var i = 0; i < $scope.raw_columns.length; i++) {
            var inner_tcm = $scope.raw_columns[i];
            inner_tcm.is_duplicate = $scope.is_tcm_duplicate(inner_tcm);
        }
    };

    /*
     * update_raw_columns: prototypical inheritance for all the raw columns
     */
    var update_raw_columns = function() {
      var raw_columns_prototype = {
        building_columns: [''].concat(
            suggested_mappings_payload.building_columns
        ),
        suggestion: '',
        user_suggestion: false,
        // Items used to create a concatenated object get set to true
        is_a_concat_parameter: false,
        // Result of a concatenation gets set to true
        is_concatenated: false,
        "find_suggested_mapping": function (suggestions) {
            var that = this;
            angular.forEach(suggestions, function(value, key) {
                // Check first element of each value to see if it matches.
                // if it does, then save that key as a suggestion
                if (key === that.name) {
                    that.suggestion = value[0];
                    that.confidence = value[1];
                }
            });
        },
        "confidence_text": function() {
          if (this.confidence < 40) {
            return "low";
          }
          if (this.confidence < 75) {
            return "med";
          }
          if (this.confidence >= 75) {
            return "high";
          }
          return "";
        }
      };
      var temp_columns = [];
      var i = 0;
      angular.forEach($scope.raw_columns, function (c) {
        var tcm = {};
        i += 1;
        tcm.name = c;
        tcm.row = i;
        tcm.raw_data = [];
        angular.forEach($scope.first_five, function(value, key) {
            angular.forEach(value, function(v, k) {
                if (k === tcm.name) {
                    tcm.raw_data.push(v);
                }
            });
        });

        angular.extend(tcm, raw_columns_prototype);
        temp_columns.push(tcm);
        tcm.find_suggested_mapping($scope.suggested_mappings);
        $scope.validate_data(tcm); // Validate our system-suggestions.
      });
      // Set the first_five to be an attribute of tcm.
      $scope.raw_columns = temp_columns;
    };

    /*
     * get_mapped_buildings: gets mapped buildings for the preview table
     */
    $scope.get_mapped_buildings = function() {
      $scope.import_file.progress = 0;
      $scope.save_mappings = true;
      $scope.review_mappings = true;
      $scope.tabs.one_active = false;
      $scope.tabs.two_active = true;
      var mapped_columns = $scope.get_mappings().map(function(d){
        return d[0];
      });
      $scope.columns = $scope.search.generate_columns(
            all_columns.fields,
            mapped_columns,
            $scope.search.column_prototype
        );
      // save as default columns
      user_service.set_default_columns(
        mapped_columns, $scope.user.show_shared_buildings
      );
      $scope.search.filter_params = {
        "import_file_id": $scope.import_file.id
      };
      $scope.show_mapped_buildings = true;
      $scope.save_mappings = false;
      $scope.search.search_buildings();
    };

    /*
     * Get_mappings
     * Pull out the mappings of the TCM objects (stored in raw_columns) list
     * into a flat data structure like so [[<dest>, <raw>], ...].
     */
    $scope.get_mappings = function(){
        var mappings = [];
        for (var i = 0; i < $scope.raw_columns.length; i++) {
            var tcm = $scope.raw_columns[i];
            // We're not mapping columns that are getting concatinated.
            if (tcm.is_a_concat_parameter){
                continue;
            }
            var header = tcm.name;
            // If we have a concatenated column, then we encode the raw_header
            // as the sources.
            if (tcm.is_concatenated) {
                header = tcm.source_headers;
            }
            mappings.push([
                tcm.suggestion, header
            ]);
        }

        return mappings;
    };

    /*
     * show_mapping_progress: shows the progress bar and kicks off the mapping,
     *   after saving column mappings
     */
    $scope.show_mapping_progress = function(){
      $scope.import_file.progress = 0;
      $scope.save_mappings = true;
      mapping_service.save_mappings(
        $scope.import_file.id,
        $scope.get_mappings()
      )
      .then(function (data){
        // start mapping
        mapping_service.start_mapping($scope.import_file.id).then(function(data){
          // save maps start mapping data
          check_mapping(data.progress_key);
        });
      });
    };

    /*
     * remap_buildings: shows the progress bar and kicks off the re-mapping,
     *   after saving column mappings, deletes unmatched buildings
     */
    $scope.remap_buildings = function(){
      $scope.import_file.progress = 0;
      $scope.save_mappings = true;
      $scope.review_mappings = true;
      mapping_service.save_mappings(
        $scope.import_file.id,
        $scope.get_mappings()
      )
      .then(function (data){
        // start re-mapping
        mapping_service.remap_buildings($scope.import_file.id).then(function(data){
          if (data.status === "error" || data.status === "warning") {
            $scope.$emit('app_error', data);
            $scope.get_mapped_buildings();
          } else {
            // save maps start mapping data
            check_mapping(data.progress_key);
          }
        });
      });
    };

    /**
     * check_mapping: mapping progress loop
     */
    var check_mapping = function (progress_key) {
      uploader_service.check_progress_loop(
        progress_key,  // key
        0, //starting prog bar percentage
        1.0,  // progress multiplier
        function(data){  //success fn
          $scope.get_mapped_buildings();
        },
        $scope.import_file  // progress bar obj
      );
    };


    /*
     * duplicates_present: used to disable or enable the 'show & review
     *   mappings' button.
     */
    $scope.duplicates_present = function() {
      for(var i=0; i < $scope.raw_columns.length; i++) {
        var tcm = $scope.raw_columns[i];
        if (tcm.is_duplicate) {
          return true;
        }
      }
      return false;
    };

    /**
     * open_edit_columns_modal: modal to set which columns a user has in the
     *   table
     */
    $scope.open_edit_columns_modal = function() {
        var modalInstance = $modal.open({
            templateUrl: urls.static_url + 'seed/partials/custom_view_modal.html',
            controller: 'custom_view_modal_ctrl',
            resolve: {
                'all_columns': function() {
                    return {
                        fields: all_columns.fields
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
                // update columns
                $scope.columns = $scope.search.generate_columns(
                    all_columns.fields,
                    columns,
                    $scope.search.column_prototype
                );
        }, function (message) {
        });
    };

    var init = function() {
        update_raw_columns();
    };
    init();

    /*
     * open_data_upload_modal: defaults to step 7, which triggers the matching
     *  process and allows the user to add more data if no matches are
     *  available
     *
     * @param {object} dataset: an the import_file's dataset. Used in the
     *   modal to display the file name and match buildings that were created
     *   from the file.
     */
    $scope.open_data_upload_modal = function(dataset) {
        var step = 11;
        var ds = angular.copy(dataset);
        ds.filename = $scope.import_file.name;
        ds.import_file_id = $scope.import_file.id;
        var dataModalInstance = $modal.open({
            templateUrl: urls.static_url + 'seed/partials/data_upload_modal.html',
            controller: 'data_upload_modal_ctrl',
            resolve: {
                step: function(){
                    return step;
                },
                dataset: function(){
                    return ds;
                }
            }
        });

    };

}]);
