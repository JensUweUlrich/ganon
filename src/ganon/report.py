import time
import os
from ganon.tax import Tax
from ganon.util import *


def report(cfg):
    #validate input input files
    rep_files = validate_input_files(cfg.rep_files, cfg.input_directory, cfg.input_extension, cfg.quiet)

    # Parse taxonomy or download new
    if cfg.db_prefix:
        dbp = []
        for prefix in cfg.db_prefix:
            if prefix.endswith(".tax"):
                dbp.append(prefix)
            else:
                dbp.append(prefix+".tax")
        tax = Tax(dbp)
    else:
        tmp_output_folder = os.path.dirname(cfg.output_prefix)
        if not tmp_output_folder:
            tmp_output_folder = "."
        tmp_output_folder += "/ganon_report_tmp/"
        if not set_tmp_folder(tmp_output_folder): return False
        # Set up taxonomy
        ncbi_nodes_file, ncbi_merged_file, ncbi_names_file = set_taxdump_files(cfg.taxdump_file, tmp_output_folder, cfg.quiet)
        tx = time.time()
        print_log("Parsing taxonomy", cfg.quiet)
        tax = Tax(ncbi_nodes=ncbi_nodes_file, ncbi_names=ncbi_names_file)
        rm_tmp_folder(tmp_output_folder)
        print_log(" - done in " + str("%.2f" % (time.time() - tx)) + "s.\n", cfg.quiet)

    any_rep = False
    print_log("Generating report(s)", cfg.quiet)
    # Parse report file
    for rep_file in rep_files:
        print_log("", cfg.quiet)

        reports, counts = parse_rep(rep_file)
        if not reports:
            print_log(" - nothing to report for " + rep_file, cfg.quiet)
            continue

        # If skipping/keeping hiearchies, remove all assignments from reports
        if cfg.skip_hierarchy or cfg.keep_hierarchy:
            reports = remove_hierarchy(reports, counts, cfg.skip_hierarchy, cfg.keep_hierarchy, cfg.quiet)

        # General output file
        if len(rep_files) == 1:
            output_file = cfg.output_prefix
        else:
            file_pre = os.path.splitext(os.path.basename(rep_file))[0]
            output_file = cfg.output_prefix+file_pre

        if cfg.split_hierarchy:
            for h in reports:
                if h not in cfg.skip_hierarchy:
                    output_file_h=output_file+"."+h+".tre"
                    r = print_final_report({h:reports[h]}, counts, tax, output_file_h, cfg)
                    if not r:
                        print_log(" - nothing to report for hierarchy " + h + " in the " + rep_file, cfg.quiet)
                        continue
                    else:
                        print_log(" - report saved to " + output_file_h, cfg.quiet)
                        any_rep = True

        else:
            output_file=output_file+".tre"
            r = print_final_report(reports, counts, tax, output_file, cfg)
            if not r:
                print_log(" - nothing to report for " + rep_file, cfg.quiet)
                continue
            else:
                print_log(" - report saved to " + output_file, cfg.quiet)
                any_rep = True

    return True if any_rep else False

def parse_rep(rep_file):
    counts = {}
    reports = {}
    total_direct_matches = 0
    with open(rep_file, 'r') as rep_file:
        for line in rep_file:
            fields = line.rstrip().split("\t")
            if fields[0] == "#total_classified":
                classified_reads = int(fields[1])
            elif fields[0] == "#total_unclassified":
                unclassified_reads = int(fields[1])
            else:
                hierarchy_name, target, direct_matches, unique_reads, lca_reads, rank, name = fields
                direct_matches = int(direct_matches)
                unique_reads = int(unique_reads)
                lca_reads = int(lca_reads)

                if hierarchy_name not in reports:
                    reports[hierarchy_name] = {}
                    counts[hierarchy_name] = {"matches": 0,
                                              "reads": 0}

                # entries should be unique by hiearchy_name
                if target not in reports[hierarchy_name]:
                    reports[hierarchy_name][target] = {"direct_matches": 0,
                                                       "unique_reads": 0,
                                                       "lca_reads": 0}

                reports[hierarchy_name][target]["direct_matches"] += direct_matches
                reports[hierarchy_name][target]["unique_reads"] += unique_reads
                reports[hierarchy_name][target]["lca_reads"] += lca_reads

                counts[hierarchy_name]["matches"] += direct_matches
                # sum up classified reads for the hiearchy
                counts[hierarchy_name]["reads"] += unique_reads + lca_reads

                total_direct_matches += direct_matches

    counts["total"] = {"matches": total_direct_matches,
                       "reads": classified_reads,
                       "unclassified": unclassified_reads}

    return reports, counts


def print_final_report(reports, counts, tax, output_file, cfg):
    if not cfg.ranks:
        all_ranks = False
        fixed_ranks = ["root",
                       "superkingdom",
                       "phylum",
                       "class",
                       "order",
                       "family",
                       "genus",
                       "species",
                       "assembly"]
    elif cfg.ranks[0] == "all":
        all_ranks = True
        fixed_ranks = []
    else:
        all_ranks = False
        fixed_ranks = ['root'] + cfg.ranks

    if cfg.report_type == "reads":
        total = counts["total"]["reads"] + counts["total"]["unclassified"]
    else:
        total = counts["total"]["matches"]

    # Count targets in the report by report type (counts or matches), merging multiple hierarchical levels
    # merged_counts[target] = {'count': INT, 'unique': INT}
    merged_counts = count_targets(reports, cfg.report_type)

    # Iterate over the taxonomic tree and sum the entries (cummulative)
    # tree_cum_counts[node] = cum_count
    tree_cum_counts = cummulative_count_tree(merged_counts,
                                             tax,
                                             all_ranks,
                                             fixed_ranks)

    # build lineage for each entry based on chosen ranks
    # lineage[node] = ["1", "1224", ..., node]
    lineage = build_lineage(tree_cum_counts, tax, all_ranks, fixed_ranks, cfg.taxids)

    # filter with fixed ranks and user parameters (names, taxid)
    # filtered_cum_counts[node] = cum_count
    unknown_taxa, filtered_cum_counts = filter_report(tree_cum_counts, lineage, tax, all_ranks, fixed_ranks, total, cfg)
    if not filtered_cum_counts:
        return False

    # sort entries based on report or user-defined
    # sorted_nodes = ["1", "1224", ...]
    sorted_nodes = sort_report(filtered_cum_counts, cfg.sort, all_ranks, fixed_ranks, lineage, tax, merged_counts)

    # Output file
    tre_file = open(output_file, 'w')
    output_rows = []

    # Reporting reads, first line prints unclassified entries
    if cfg.report_type=="reads":
        unclassified_line = ["unclassified","-","-","unclassified","0","0","0",str(counts["total"]["unclassified"]),str("%.5f" % ((counts["total"]["unclassified"]/total)*100))]
        if cfg.output_format in ["tsv","csv"]:
            print(*unclassified_line, file=tre_file, sep="\t" if cfg.output_format=="tsv" else ",")
        else:
            output_rows.append(unclassified_line)

    # All entries
    for node in sorted_nodes:
        n = tax.get_node(node)
        rank = n['rank']
        name = n["name"]

        unique = merged_counts[node]['unique'] if node in merged_counts else 0
        lca = merged_counts[node]['count'] if node in merged_counts else 0
        cum_count = filtered_cum_counts[node]
        cum_count_perc = (filtered_cum_counts[node]/total)*100
        children = cum_count - unique - lca

        out_line = [rank, node, "|".join(lineage[node]), name, str(unique), str(lca), str(children), str(cum_count), str("%.5f" % cum_count_perc)]
        if cfg.output_format in ["tsv","csv"]:
            print(*out_line, file=tre_file, sep="\t" if cfg.output_format=="tsv" else ",")
        else:
            output_rows.append(out_line)

    # Print formated text
    if cfg.output_format=="text":
        # Check max width for each col
        max_width = [0]*len(output_rows[0])
        for row in output_rows:
            for i,w in enumerate(max_width):
                l = len(row[i])
                if l > w: max_width[i]=l
        # apply format when printing with max_width
        for row in output_rows:
            print("\t".join(['{0: <{width}}'.format(field, width=max_width[i]) for i,field in enumerate(row)]), file=tre_file)

    if output_file:
        tre_file.close()
    if unknown_taxa:
        print_log(" - " + str(unknown_taxa) + " taxa not found in the taxonomy. Those entries are counted as orphan nodes (with root as parent node). Too report them, use --ranks all or add 'na' to the end of ranks list (e.g. --ranks genus species na)", cfg.quiet)
    print_log(" - " + str(len(sorted_nodes)) + " taxa reported", cfg.quiet)
    return True


def count_targets(reports, report_type):
    merged_counts = {}
    for hierarchy_name, report in reports.items():
        for target, rep in report.items():
            if report_type == "reads":
                # if there were reads assigned to the target (not only shared matches)
                if rep['unique_reads'] + rep['lca_reads']:
                    if target not in merged_counts:
                        merged_counts[target] = {'unique': 0, 'count': 0}
                    merged_counts[target]['unique'] += rep['unique_reads']
                    merged_counts[target]['count'] += rep['lca_reads']
            else:
                # If there were any matches to the target
                if rep['direct_matches']:
                    if target not in merged_counts:
                        merged_counts[target] = {'unique':0, 'count': 0}
                    merged_counts[target]['unique'] += rep['unique_reads']
                    # count of matches already has unique included
                    # it needs to be subtracted to fit the same model as the report type reads when printing
                    merged_counts[target]['count'] += rep['direct_matches']-rep['unique_reads']
    return merged_counts


def cummulative_count_tree(merged_counts, tax, all_ranks, fixed_ranks):
    filtered_cum_counts = {}
    for leaf in merged_counts.keys():
        sum_count = merged_counts[leaf]['unique'] + merged_counts[leaf]['count']
        t = leaf
        while t != "0":
            if t not in filtered_cum_counts:
                filtered_cum_counts[t] = 0
            n = tax.get_node(t)
            filtered_cum_counts[t] += sum_count
            t = n["parent"]
    return filtered_cum_counts


def build_lineage(filtered_cum_counts, tax, all_ranks, fixed_ranks, taxids):
    lineage = {}
    for node in filtered_cum_counts:
        if all_ranks:
            lineage[node] = []
            t=node
            while t != "0":
                lineage[node].insert(0,t)
                t = tax.get_node(t)["parent"]
        else:
            t, r = tax.get_node_rank_fixed(node, fixed_ranks)
            # Special case rank is "na" -> node without defined rank, lineage under root
            if r == "na":
                lineage[node] = ["1", node]
            elif r in fixed_ranks:
                lineage[node]=[]
                max_rank_idx = fixed_ranks.index(r) # get index of current rank
                while t!="0":
                    # Add empty || if fixed rank is missing
                    for i in range(max_rank_idx-fixed_ranks.index(r)):
                        lineage[node].insert(0,"")
                        max_rank_idx -= 1
                    lineage[node].insert(0, t)
                    max_rank_idx -= 1
                    t, r = tax.get_node_rank_fixed(tax.get_node(t)["parent"], fixed_ranks)

    return lineage


def filter_report(tree_cum_counts, lineage, tax, all_ranks, fixed_ranks, total, cfg):
    filtered_cum_counts = {}
    unknown_taxa = 0
    for node, cum_count in tree_cum_counts.items():
        r = tax.get_node(node)
        # always keep root
        if r['rank'] == "root":
            filtered_cum_counts[node] = cum_count
            continue

        # mark unknown rank
        if r['rank'] == "na":
            unknown_taxa += 1

        # keep only selected fixed_ranks
        if not all_ranks and r['rank'] not in fixed_ranks:
            continue
        # Filter by value
        if cfg.min_count:
            if cfg.min_count > 1 and cum_count < cfg.min_count:
                continue
            elif cfg.min_count < 1 and (cum_count/total) < cfg.min_count:
                continue

        if cfg.max_count:
            if cfg.max_count > 1 and cum_count > cfg.max_count:
                continue
            elif cfg.max_count < 1 and (cum_count/total) > cfg.max_count:
                continue

        if cfg.taxids and node != "1" and not any(t in cfg.taxids for t in lineage[node]):
            continue
        if cfg.names and not r["name"] in cfg.names:
            continue
        if cfg.names_with and not any(n in r["name"] for n in cfg.names_with):
            continue

        filtered_cum_counts[node] = cum_count
    return unknown_taxa, filtered_cum_counts


def sort_report(filtered_cum_counts, sort, all_ranks, fixed_ranks, lineage, tax, merged_counts):

    # Always keep root at the top
    # Sort report entries, return sorted keys of the dict
    if not sort: # not user-defined, use defaults
        if all_ranks:
            sorted_nodes = sorted(filtered_cum_counts, key=lambda k: lineage[k])
        else:
            sorted_nodes = sorted(filtered_cum_counts, key=lambda k: (fixed_ranks.index(tax.get_node(k)['rank']), -filtered_cum_counts[k]), reverse=False)
    else: # user-defined
        if sort=="lineage":
            sorted_nodes = sorted(filtered_cum_counts, key=lambda k: lineage[k])
        elif sort=="rank":
            if all_ranks: # if sorting by rank showing all ranks, order of the ranks is not know, sort them alphabetically
                sorted_nodes = sorted(filtered_cum_counts, key=lambda k: (tax.get_node(k)['rank'], -filtered_cum_counts[k]), reverse=False)
            else:
                sorted_nodes = sorted(filtered_cum_counts, key=lambda k: (fixed_ranks.index(tax.get_node(k)['rank']), -filtered_cum_counts[k]), reverse=False)
        elif sort=="unique":
            sorted_nodes = sorted(filtered_cum_counts, key=lambda k: (-merged_counts[k]['unique'] if k in merged_counts else 0, -filtered_cum_counts[k]), reverse=False)
        else: # sort=="count"
            sorted_nodes = sorted(filtered_cum_counts, key=lambda k: -filtered_cum_counts[k], reverse=False)

    # Move root to the front to print always first first
    sorted_nodes.insert(0, sorted_nodes.pop(sorted_nodes.index("1")))

    return sorted_nodes

def remove_hierarchy(reports, counts, skip, keep, quiet):
    # In case of skipped hiearchy, account all matches to root node
    for hierarchy_name in list(reports.keys()):
        # Skiped report
        if hierarchy_name in skip or (keep and hierarchy_name not in keep):
            del reports[hierarchy_name]
            print_log(" - skipped " + str(counts[hierarchy_name]["reads"])  + " reads with " + str(counts[hierarchy_name]["matches"]) + " matches for " + hierarchy_name, quiet)

    return reports
