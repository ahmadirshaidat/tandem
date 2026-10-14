# ADR 0009: Decimal fractional ranks

Status: accepted for Slice 3.

Tasks have PostgreSQL NUMERIC(38,18) ranks, ordered by rank and ID within project/status. New cards append in steps of 1024; moves use the midpoint of adjacent ranks. A normal move updates only the moved task, with version and rank/status activity in one transaction. Neighbor references must belong to the destination project/status; outdated adjacent references return 409.

When a gap shrinks below 10^-15, rebalance that column to multiples of 1024. Every rank changed by this rare operation receives activity, a version increment and a replayable move event. Fifty digits of decimal arithmetic avoid midpoint rounding before persistence. Clients compare fixed-point decimal strings without converting to floating point. Workspace serialization plus optimistic versions gives concurrent moves a deterministic winner.
