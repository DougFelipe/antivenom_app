/**
 * @fileoverview Data service for SINAN occurrence metrics.
 *
 * Loads converted occurrence metrics from JSON.
 *
 * @module infrastructure/data/occurrenceMetricsData
 */

import { createLogger } from '../logging/logger';

const logger = createLogger('OccurrenceMetricsData');

export interface YearlyOccurrenceData {
    readonly year: number;
    readonly occurrences: number;
    readonly incidence: number;
    readonly lethality: number;
}

export interface TimeToCareData {
    readonly bucket: string;
    readonly label: string;
    readonly count: number;
    readonly percentage: number;
}

export interface OccurrenceSummary {
    readonly totalOccurrences: number;
    readonly averageIncidence: number;
    readonly lethalityRate: number;
}

export interface OccurrenceRegionData {
    readonly region: string;
    readonly totalOccurrences: number;
    readonly stateCount: number;
    readonly percentageOfBrazil: number;
}

export interface OccurrenceStateData {
    readonly uf: string;
    readonly state: string;
    readonly region: string;
    readonly totalOccurrences: number;
    readonly percentageOfBrazil: number;
    readonly incidenceCoefficient: number;
    readonly lethalityRate: number;
    readonly yearly: YearlyOccurrenceData[];
}

export interface OccurrenceMetricsData {
    readonly metadata: {
        readonly sourceFile: string;
        readonly generatedAt: string;
        readonly years: number[];
        readonly totalRows: number;
        readonly stateRows: number;
    };
    readonly summary: OccurrenceSummary;
    readonly brazilByYear: YearlyOccurrenceData[];
    readonly timeToCareBrazil: TimeToCareData[];
    readonly byRegion: OccurrenceRegionData[];
    readonly byState: OccurrenceStateData[];
}

/** Cached occurrence metrics data. */
let occurrenceMetricsCache: OccurrenceMetricsData | null = null;

/**
 * Load occurrence metrics from JSON database.
 * Results are cached after first load.
 */
export async function loadOccurrenceMetrics(): Promise<OccurrenceMetricsData> {
    if (occurrenceMetricsCache) {
        return occurrenceMetricsCache;
    }

    try {
        const response = await fetch('/data/occurrence_metrics.json');
        if (!response.ok) {
            throw new Error(`Failed to load occurrence metrics: ${response.status}`);
        }

        const data = (await response.json()) as OccurrenceMetricsData;
        occurrenceMetricsCache = data;
        logger.info(`Loaded occurrence metrics for ${data.byState.length} states`);
        return data;
    } catch (error) {
        logger.error(
            `Failed to load occurrence metrics: ${error instanceof Error ? error.message : String(error)}`
        );
        throw error;
    }
}
