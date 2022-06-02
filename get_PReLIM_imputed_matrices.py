import pandas as pd
import numpy as np
from clubcpg.ParseBam import BamFileReadParser
from multiprocessing import Pool
from collections import defaultdict
import time
from pandas.core.indexes.base import InvalidIndexError
import os
import logging
from clubcpg_prelim import PReLIM
import argparse


def create_dictionary(bins, matrices):
    output = dict()
    for b, m in zip(bins, matrices):
        output[b] = m

    return output


def get_chromosome_lengths(input_bam_file):
    """
    Get dictionary containing lengths of the chromosomes. Uses bam file for reference

    :return: Dictionary of chromosome lengths, ex: {"chrX": 222222}
    """
    parser = BamFileReadParser(input_bam_file, 20)
    return dict(zip(parser.OpenBamFile.references, parser.OpenBamFile.lengths))


def remove_scaffolds(chromosome_len_dict):
    """
    Return a dict containing only the standard chromosomes starting with "chr"

    :param chromosome_len_dict: A dict generated by get_chromosome_lenghts()
    :return: a dict containing only chromosomes starting with "chr"
    """
    new_dict = dict(chromosome_len_dict)
    for key in chromosome_len_dict.keys():
        if not key.startswith("chr"):
            new_dict.pop(key)

    return new_dict


def generate_bins_list(bin_size, chromosome_len_dict):
    """
    Get a dict of lists of all bins according to desired bin size for all chromosomes in the passed dict

    :param chromosome_len_dict: A dict of chromosome length sizes from get_chromosome_lenghts, cleaned up by remove_scaffolds() if desired
    :return: dict with each key being a chromosome. ex: chr1
    """
    all_bins = defaultdict(list)
    for key, value in chromosome_len_dict.items():
        bins = list(np.arange(bin_size, value + bin_size, bin_size))
        bins = ["_".join([key, str(x)]) for x in bins]
        all_bins[key].extend(bins)

    return all_bins


# Track the progress of the multiprocessing and output
def track_progress(job, update_interval=60):
    while job._number_left > 0:
        logging.info("Tasks remaining = {0}".format(
            job._number_left * job._chunksize))
        time.sleep(update_interval)


def calculate_bin_coverage(bin):
    """
    Take a single bin, return a matrix. This is passed to a multiprocessing Pool.

    :param bin: Bin should be passed as "Chr19_4343343"
    :return: pd.DataFrame with rows containing NaNs dropped
    """
    bins_no_reads = 0
    # Get reads from bam file
    parser = BamFileReadParser(input_bam, 20, None, None, None, None, True)
    # Split bin into parts
    chromosome, bin_location = bin.split("_")
    bin_location = int(bin_location)
    try:
        reads = parser.parse_reads(chromosome, bin_location - bin_size, bin_location)
        matrix = parser.create_matrix(reads)
    except BaseException as e:
        # No reads are within this window, do nothing
        bins_no_reads += 1
        return None
    except:
        logging.error("Unknown error: {}".format(bin))
        return None

    # drop rows of ALL NaN
    matrix = matrix.dropna(how="all")
    # convert to data_frame of 1s and 0s, drop rows with NaN
    # matrix = matrix.dropna()
    # if matrix is empty, attempt to create it with correction before giving up
    if len(matrix) == 0:
        original_matrix = matrix.copy()
        reads = parser.correct_cpg_positions(reads)
        try:
            matrix = parser.create_matrix(reads)
        except InvalidIndexError as e:
            logging.error("Invalid Index error when creating matrices at bin {}".format(bin))
            logging.debug(str(e))
            return bin, original_matrix
        except ValueError as e:
            logging.error("Matrix concat error ar bin {}".format(bin))
            logging.debug(str(e))

        matrix = matrix.dropna()
        if len(matrix) > 0:
            logging.info("Correction attempt at bin {}: SUCCESS".format(bin))
        else:
            logging.info("Correction attempt at bin {}: FAILED".format(bin))

    return bin, matrix


def postprocess_predictions(predicted_matrix):
    """Takes array with predicted values and rounds them to 0 or 1 if threshold is exceeded

    Arguments:
        predicted_matrix {[type]} -- matrix generated by imputation

    Returns:
        [type] -- predicted matrix predictions as 1, 0, or NaN
    """

    processed_array = []
    for array in predicted_matrix:
        new_array = []
        for item in array:
            if item != 1 and item != 0:
                if item <= 0.2:  # TODO un-hardcode this
                    new_array.append(0.0)
                elif item >= 0.8:  # TODO un-hardcode this
                    new_array.append(1.0)
                else:
                    new_array.append(np.nan)
            else:
                new_array.append(item)

        processed_array.append(new_array)

    return np.array(processed_array)


def write_imputed_matrices(cpg_density, matrix_list, bin_list):
    output_imputed_file = "./%s/PReLIM.Sample.%s.%s_IMPUTED_CPG%s.txt" % (
        output_directory, input_bam.split("/")[-1], individual_chrom, cpg_density)
    output_imputed_file_npy = "./%s/PReLIM.Sample.%s.%s_IMPUTED_CPG%s.npy" % (
        output_directory, input_bam.split("/")[-1], individual_chrom, cpg_density)
    np.save(output_imputed_file_npy, dict(zip(bin_list, matrix_list)))
    with open(output_imputed_file, 'w+') as f:
        f.write("IMPUTED MATRIX COUNT : %s \n" % (len(matrix_list)))
        for b, m in zip(bin_list, matrix_list):
            f.write(b)
            matrix_string = '\n'.join('\t'.join('%s' % x for x in y) for y in m)
            f.write("\n")
            f.write(matrix_string)
            f.write("\n")


def write_initial_matrices(output_file, initial_matrices, output_file_npy):
    with open(output_file, 'w+') as f:
        temp_dict = {}
        bin_count = 0
        for r in initial_matrices:
            if r:
                df_string = r[1].to_string(header=False, index=False)
                f.write(r[0])
                f.write("\n")
                f.write(df_string)
                f.write("\n")
                bin_count += 1
                temp_dict[r[0]] = r[1].to_numpy(dtype=float)
        np.save(output_file_npy, temp_dict)
        f.write("BIN COUNT : %s ...\n" % (bin_count))


def get_PReLIM_imputed_matrices(bin_size, input_bam, output_directory, individual_chrom):
    chromosome_lengths = get_chromosome_lengths(input_bam)
    chromosome_lengths = remove_scaffolds(chromosome_lengths)

    # If one chromosome was specified use only that chromosome
    if individual_chrom:
        new = dict()
        new[individual_chrom] = chromosome_lengths[individual_chrom]
        chromosome_lengths = new

    bins_to_analyze = generate_bins_list(bin_size, chromosome_lengths)

    # Set up for multiprocessing
    # Loop over bin dict and pool.map them individually
    final_results = []
    for key in bins_to_analyze.keys():
        pool = Pool(processes=24)
        results = pool.map_async(calculate_bin_coverage, bins_to_analyze[key])

        track_progress(results)
        # once done, get results
        results = results.get()

        final_results.extend(results)

    print("Analysis complete")
    logging.info("Analysis complete")

    # Write pre-imputed matrices to output file
    output_file = "./%s/PReLIM.Sample.%s.%s.txt" % (output_directory, input_bam.split("/")[-1], individual_chrom)
    output_file_npy = "./%s/PReLIM.Sample.%s.%s.npy" % (output_directory, input_bam.split("/")[-1], individual_chrom)
    write_initial_matrices(output_file, final_results, output_file_npy)

    bins = []
    matrices = []
    cpg2_matrix_list = []
    cpg2_bin_list = []
    cpg3_matrix_list = []
    cpg3_bin_list = []
    cpg4_matrix_list = []
    cpg4_bin_list = []
    cpg5_matrix_list = []
    cpg5_bin_list = []
    other_bin_list = []
    other_matrix_list = []

    for r in final_results:
        if r:
            if r[1].shape[1] == 2:
                cpg2_bin_list.append(r[0])
                cpg2_matrix_list.append(r[1].fillna(-1).to_numpy(dtype=float))
            elif r[1].shape[1] == 3:
                cpg3_bin_list.append(r[0])
                cpg3_matrix_list.append(r[1].fillna(-1).to_numpy(dtype=float))
            elif r[1].shape[1] == 4:
                cpg4_bin_list.append(r[0])
                cpg4_matrix_list.append(r[1].fillna(-1).to_numpy(dtype=float))
            elif r[1].shape[1] == 5:
                cpg5_bin_list.append(r[0])
                cpg5_matrix_list.append(r[1].fillna(-1).to_numpy(dtype=float))
            else:
                other_bin_list.append(r[0])
                other_matrix_list.append(r[1].fillna(-1).to_numpy(dtype=float))

    bins.append(cpg2_bin_list)
    bins.append(cpg3_bin_list)
    bins.append(cpg4_bin_list)
    bins.append(cpg5_bin_list)

    matrices.append(cpg2_matrix_list)
    matrices.append(cpg3_matrix_list)
    matrices.append(cpg4_matrix_list)
    matrices.append(cpg5_matrix_list)

    for i in range(2, 6):
        # Step 2: Created a model with correct density for given bins
        model = PReLIM(cpgDensity=i)

        # Step 3: Train the model and save it if you wish
        model.train(matrices[i - 2], model_file="model_file_cpg%s" % i)

        print("TRAINING COMPLETED FOR CPG DENSITY %s ..." % i)

        # ... use batch imputation to impute many bins at once (recommended)
        imputed_bins = model.impute_many(matrices[i - 2])

        imputed_matrix_list = []
        for matrix in imputed_bins:
            imputed_matrix = postprocess_predictions(matrix)
            imputed_matrix_list.append(imputed_matrix)

        print("IMPUTING COMPLETED FOR CPG DENSITY %s ..." % i)
        write_imputed_matrices(i, imputed_matrix_list, bins[i - 2])


# Script begins
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("bin_size", help="Size of bins to group the data into", default=100)
    parser.add_argument("input_bam_file",
                        help="Input bam file, coordinate sorted with index present", default=None)
    parser.add_argument("-chr", "--chromosome", help="Optional, perform only on one chromosome. ")
    parser.add_argument("-o", "--output", help="folder to save imputed coverage data", default=None)

    args = parser.parse_args()

    # Set output dir
    if not args.output:
        output_folder = os.path.dirname(args.input_bam_file)
    else:
        output_folder = args.output

    try:
        os.mkdir(output_folder)
    except FileExistsError:
        print("Output folder already exists... no need to create it...")

    bin_size = int(args.bin_size)
    input_bam = args.input_bam_file
    output_directory = output_folder
    individual_chrom = args.chromosome

    get_PReLIM_imputed_matrices(bin_size, input_bam, output_directory, individual_chrom)
