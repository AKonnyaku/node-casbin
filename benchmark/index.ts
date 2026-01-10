
import * as path from 'path';
import * as benchmark from 'benchmark';
import { addEnforcerBenchmarks } from './enforcer_benchmark';
import { addCachedEnforcerBenchmarks } from './cached_enforcer_benchmark';
import { addManagementApiBenchmarks } from './management_api_benchmark';
import { addRoleManagerBenchmarks } from './role_manager_benchmark';

const suite = new benchmark.Suite();

(async () => {
    console.log('Running benchmarks...');

    // Add all benchmarks
    await addEnforcerBenchmarks(suite);
    await addCachedEnforcerBenchmarks(suite);
    await addManagementApiBenchmarks(suite);
    await addRoleManagerBenchmarks(suite);

    suite
        .on('cycle', (event: any) => {
            console.log(String(event.target));
        })
        .on('complete', function (this: any) {
            console.log('Benchmark finished.');
        })
        .run({ 'async': true });
})();
