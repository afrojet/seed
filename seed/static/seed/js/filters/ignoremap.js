/**
 * :copyright: (c) 2014 Building Energy Inc
 * :license: BSD 3-Clause, see LICENSE for more details.
 */
angular.module('ignoremap', []).filter('ignoremap', [
  '$filter',
  function($filter) {

    return function(input) {
        if (typeof input === 'undefined' || input === null || input === "") {
            return "------ Ignore Row ------";
        }
        return input;
    };

}]);